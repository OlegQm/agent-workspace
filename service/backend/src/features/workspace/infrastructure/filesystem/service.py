"""Provide safe operations for agent workspace files."""

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from fastapi import HTTPException, UploadFile, status


@dataclass(frozen=True)
class WorkspaceFilesystem:
    """Perform path-safe file operations within one workspace root."""

    root: Path

    @property
    def resolved_root(self) -> Path:
        """Return the canonical workspace root."""
        return self.root.resolve()

    def resolve(self, relative: str = "", *, must_exist: bool = False) -> Path:
        """Resolve one relative path without allowing workspace escape or symlinks."""
        relative_path = Path(relative)
        if (
            relative_path.is_absolute()
            or "\x00" in relative
            or any(part == ".." for part in relative_path.parts)
        ):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid path")
        root = self.resolved_root
        if not relative:
            return root
        candidate = root.joinpath(relative_path)
        try:
            parent = candidate.parent.resolve(strict=True)
        except FileNotFoundError:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Parent not found")
        try:
            parent.relative_to(root)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Path escapes workspace"
            )
        result = parent / candidate.name
        try:
            result.resolve(strict=False).relative_to(root)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Path escapes workspace"
            )
        if result.is_symlink():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Symlinks are not allowed"
            )
        if must_exist and not result.exists():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Path not found")
        return result

    def size(self) -> int:
        """Return the total size of regular files below the workspace root."""
        total = 0
        for current_root, directories, files in os.walk(self.root, followlinks=False):
            directories[:] = [
                directory
                for directory in directories
                if not (Path(current_root) / directory).is_symlink()
            ]
            for name in files:
                path = Path(current_root) / name
                if not path.is_symlink():
                    total += path.stat().st_size
        return total

    def list(self, relative: str = "") -> list[dict]:
        """List regular entries in one workspace directory."""
        directory = self.resolve(relative, must_exist=True) if relative else self.resolved_root
        if not directory.is_dir():
            raise HTTPException(status_code=400, detail="Path is not a directory")
        entries = []
        for path in sorted(
            directory.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower())
        ):
            if path.is_symlink():
                continue
            stat = path.stat()
            entries.append(
                {
                    "name": path.name,
                    "path": str(path.relative_to(self.root)),
                    "type": "directory" if path.is_dir() else "file",
                    "size": stat.st_size if path.is_file() else None,
                    "modified_at": stat.st_mtime,
                }
            )
        return entries

    async def save_upload(
        self,
        upload: UploadFile,
        destination: Path,
        max_file_bytes: int,
        max_workspace_bytes: int,
    ) -> int:
        """Persist an upload while enforcing file and workspace size limits."""
        current_size = self.size()
        written = 0
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            with destination.open("xb") as target:
                while chunk := await upload.read(1024 * 1024):
                    written += len(chunk)
                    if written > max_file_bytes or current_size + written > max_workspace_bytes:
                        raise HTTPException(status_code=413, detail="Workspace limit exceeded")
                    target.write(chunk)
        except FileExistsError:
            raise HTTPException(status_code=409, detail="File already exists")
        except Exception:
            destination.unlink(missing_ok=True)
            raise
        return written

    def rename(self, relative: str, new_name: str) -> Path:
        """Rename a workspace entry without moving it to another directory."""
        source = self.resolve(relative, must_exist=True)
        if source == self.resolved_root:
            raise HTTPException(status_code=400, detail="Workspace root cannot be renamed")

        name = new_name.strip()
        if (
            not name
            or name in {".", ".."}
            or "/" in name
            or "\\" in name
            or "\x00" in name
            or len(os.fsencode(name)) > 255
        ):
            raise HTTPException(status_code=400, detail="Invalid file or folder name")

        destination_relative = str(Path(relative).parent / name)
        if Path(relative).parent == Path("."):
            destination_relative = name
        destination = self.resolve(destination_relative)
        if destination.exists():
            raise HTTPException(status_code=409, detail="Path already exists")
        source.rename(destination)
        return destination


def safe_path(root: Path, relative: str = "", *, must_exist: bool = False) -> Path:
    """Resolve one safe path through a workspace filesystem instance."""
    return WorkspaceFilesystem(root).resolve(relative, must_exist=must_exist)


def workspace_size(root: Path) -> int:
    """Return workspace size through a workspace filesystem instance."""
    return WorkspaceFilesystem(root).size()


def list_directory(root: Path, relative: str = "") -> list[dict]:
    """List a directory through a workspace filesystem instance."""
    return WorkspaceFilesystem(root).list(relative)


async def save_upload(
    upload: UploadFile, destination: Path, max_file_bytes: int, max_workspace_bytes: int, root: Path
) -> int:
    """Persist an upload through a workspace filesystem instance."""
    return await WorkspaceFilesystem(root).save_upload(
        upload,
        destination,
        max_file_bytes,
        max_workspace_bytes,
    )


def remove_path(path: Path) -> None:
    """Handle remove path."""
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()


def rename_path(root: Path, relative: str, new_name: str) -> Path:
    """Rename a workspace entry without moving it to another directory."""
    return WorkspaceFilesystem(root).rename(relative, new_name)
