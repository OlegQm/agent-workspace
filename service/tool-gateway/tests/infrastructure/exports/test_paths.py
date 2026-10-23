"""Test role-scoped export path resolution."""

from pathlib import Path

import pytest

from tool_gateway.infrastructure.configuration.settings import Settings
from tool_gateway.infrastructure.exports.paths import ExportPathResolver

settings = Settings()


def configure_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point test settings at an isolated workspace and return its root."""
    monkeypatch.setattr(settings, "agent_data_dir", tmp_path)
    root = tmp_path / "assistant/workspace"
    root.mkdir(parents=True)
    return root


def test_resolve_validates_location_suffix_and_symlinks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reject unsafe destinations and resolve a valid nested export path."""
    root = configure_workspace(tmp_path, monkeypatch)
    resolver = ExportPathResolver(settings)
    for destination in ("", "/tmp/result.csv", "result.csv", "outputs/../../escaped.csv"):
        with pytest.raises(ValueError):
            resolver.resolve(destination, {".csv"})
    with pytest.raises(ValueError, match="end with"):
        resolver.resolve("outputs/result.exe", {".csv"})

    target = root / "outputs/link.csv"
    target.parent.mkdir()
    target.symlink_to(root / "missing.csv")
    with pytest.raises(ValueError, match="symlink"):
        resolver.resolve("outputs/link.csv", {".csv"})

    assert resolver.resolve("outputs/nested/result.csv", {".csv"}) == (
        root / "outputs/nested/result.csv"
    )
