"""Test files behavior."""

from pathlib import Path

import pytest
from fastapi import HTTPException, UploadFile
from starlette.datastructures import Headers

from features.workspace.infrastructure.filesystem.service import (
    list_directory,
    remove_path,
    rename_path,
    safe_path,
    save_upload,
    workspace_size,
)


def test_safe_path_stays_inside_workspace(tmp_path: Path) -> None:
    """Verify that safe path stays inside workspace."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "reports").mkdir()

    assert safe_path(workspace, "reports/result.xlsx") == workspace / "reports/result.xlsx"


@pytest.mark.parametrize("path", ["..", "../outside", "reports/../../outside", "/etc/passwd"])
def test_safe_path_rejects_escape(tmp_path: Path, path: str) -> None:
    """Verify that safe path rejects escape."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "reports").mkdir()

    with pytest.raises(HTTPException):
        safe_path(workspace, path)


def test_safe_path_rejects_symlink(tmp_path: Path) -> None:
    """Verify that safe path rejects symlink."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (workspace / "linked").symlink_to(outside, target_is_directory=True)

    with pytest.raises(HTTPException):
        safe_path(workspace, "linked/secret.txt")


def test_rename_path_renames_file_in_current_directory(tmp_path: Path) -> None:
    """Verify that a file can be safely renamed without moving it."""
    workspace = tmp_path / "workspace"
    reports = workspace / "reports"
    reports.mkdir(parents=True)
    (reports / "draft.xlsx").write_bytes(b"report")

    destination = rename_path(workspace, "reports/draft.xlsx", "final.xlsx")

    assert destination == reports / "final.xlsx"
    assert destination.read_bytes() == b"report"
    assert not (reports / "draft.xlsx").exists()


@pytest.mark.parametrize("name", ["", ".", "..", "../secret", "nested/file", "nested\\file"])
def test_rename_path_rejects_invalid_names(tmp_path: Path, name: str) -> None:
    """Verify that rename cannot move an entry or escape the workspace."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "report.xlsx").touch()

    with pytest.raises(HTTPException):
        rename_path(workspace, "report.xlsx", name)


def test_rename_path_does_not_replace_existing_entry(tmp_path: Path) -> None:
    """Verify that rename preserves an existing destination."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "draft.xlsx").write_text("draft")
    (workspace / "final.xlsx").write_text("final")

    with pytest.raises(HTTPException) as error:
        rename_path(workspace, "draft.xlsx", "final.xlsx")

    assert error.value.status_code == 409
    assert (workspace / "final.xlsx").read_text() == "final"


@pytest.mark.unit
async def test_filesystem_listing_upload_limits_and_removal(tmp_path: Path) -> None:
    """Preserve directory ordering, upload limits, and recursive removal semantics."""
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "z-file.txt").write_text("z")
    (root / "A-folder").mkdir()
    assert [item["name"] for item in list_directory(root)] == ["A-folder", "z-file.txt"]
    assert workspace_size(root) == 1
    with pytest.raises(HTTPException, match="not a directory"):
        list_directory(root, "z-file.txt")
    upload = UploadFile(
        filename="upload.txt",
        file=__import__("io").BytesIO(b"hello"),
        headers=Headers({"content-type": "text/plain"}),
    )
    target = root / "upload.txt"
    assert await save_upload(upload, target, 10, 10, root) == 5
    with pytest.raises(HTTPException) as error:
        await save_upload(upload, target, 10, 10, root)
    assert error.value.status_code == 409
    too_large = UploadFile(filename="large.txt", file=__import__("io").BytesIO(b"toolarge"))
    with pytest.raises(HTTPException) as limit:
        await save_upload(too_large, root / "large.txt", 3, 100, root)
    assert limit.value.status_code == 413
    remove_path(root / "A-folder")
    remove_path(target)
    assert not (root / "A-folder").exists()
    assert not target.exists()


@pytest.mark.unit
def test_filesystem_symlink_and_root_rename_branches(tmp_path: Path) -> None:
    """Preserve symlink omission, size exclusion, and workspace-root rename rejection."""
    root = tmp_path / "workspace"
    root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("outside")
    link = root / "link.txt"
    link.symlink_to(outside)
    assert list_directory(root) == []
    assert workspace_size(root) == 0
    with pytest.raises(HTTPException, match="root cannot be renamed"):
        rename_path(root, "", "renamed")

    internal = root / "internal.txt"
    internal.write_text("internal")
    internal_link = root / "internal-link.txt"
    internal_link.symlink_to(internal)
    with pytest.raises(HTTPException, match="Symlinks are not allowed"):
        safe_path(root, "internal-link.txt")

    with pytest.raises(HTTPException, match="escapes workspace"):
        safe_path(root, "link.txt")

    outside_directory = tmp_path / "outside"
    outside_directory.mkdir()
    directory_link = root / "outside-link"
    directory_link.symlink_to(outside_directory, target_is_directory=True)
    with pytest.raises(HTTPException, match="escapes workspace"):
        safe_path(root, "outside-link/file.txt")


@pytest.mark.unit
def test_safe_path_exercises_workspace_error_contracts(tmp_path: Path) -> None:
    """Preserve missing-parent, missing-file, null-byte, and root-path handling."""
    root = tmp_path / "workspace"
    root.mkdir()
    assert safe_path(root) == root
    with pytest.raises(HTTPException, match="Parent not found"):
        safe_path(root, "missing/file.txt")
    with pytest.raises(HTTPException, match="Path not found"):
        safe_path(root, "missing.txt", must_exist=True)
    with pytest.raises(HTTPException, match="Invalid path"):
        safe_path(root, "bad\x00path")
