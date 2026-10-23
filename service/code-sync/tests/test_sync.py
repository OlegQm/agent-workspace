"""Test sync behavior."""

import json
import subprocess

import pytest
import yaml

from code_sync import main


def git(repository, *arguments: str) -> str:
    """Verify git."""
    result = subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def commit(repository, content: str) -> str:
    """Verify commit."""
    (repository / "README.md").write_text(content)
    git(repository, "add", "README.md")
    git(repository, "commit", "-m", content)
    return git(repository, "rev-parse", "HEAD")


def test_sync_is_atomic_and_retains_last_successful_snapshot(tmp_path, monkeypatch) -> None:
    """Verify that sync is atomic and retains last successful snapshot."""
    source = tmp_path / "source"
    source.mkdir()
    git(source, "init", "-b", "main")
    git(source, "config", "user.email", "test@example.invalid")
    git(source, "config", "user.name", "Test")
    first = commit(source, "first")

    config = tmp_path / "repositories.yaml"
    config.write_text(
        yaml.safe_dump(
            {"repositories": {"demo": {"url": str(source), "branch": "main"}}}
        )
    )
    monkeypatch.setattr(main, "CONFIG", config)
    monkeypatch.setattr(main, "DATA", tmp_path / "data")

    assert main.sync_all() == 0
    assert (main.DATA / "demo/current").resolve().name == first

    second = commit(source, "second")
    assert main.sync_all() == 0
    assert (main.DATA / "demo/current").resolve().name == second
    assert (main.DATA / "demo/previous").resolve().name == first

    source.rename(tmp_path / "source-unavailable")
    assert main.sync_all() == 1
    assert (main.DATA / "demo/current").resolve().name == second
    state = json.loads((main.DATA / "demo/state.json").read_text())
    assert state["status"] == "stale"
    assert state["current_commit"] == second


def test_github_sync_fails_locally_without_token(tmp_path, monkeypatch) -> None:
    """Verify that github sync fails locally without token."""
    token = tmp_path / "github-token"
    token.write_text("")
    monkeypatch.setattr(main, "GITHUB_TOKEN_FILE", token)

    with pytest.raises(RuntimeError, match="not configured"):
        main.require_remote_credential("https://github.com/example/private.git")


def test_empty_repository_inventory_is_a_successful_noop(tmp_path, monkeypatch) -> None:
    """An unconfigured workspace should not contact placeholder repositories."""
    config = tmp_path / "repositories.yaml"
    config.write_text("repositories: {}\n")
    monkeypatch.setattr(main, "CONFIG", config)
    monkeypatch.setattr(main, "DATA", tmp_path / "data")

    assert main.repositories() == {}
    assert main.sync_all() == 0
    assert main.status() == 0
    assert not main.DATA.exists()


def test_repository_inventory_rejects_unsafe_aliases(tmp_path, monkeypatch) -> None:
    """Aliases must remain safe as filesystem directory names."""
    config = tmp_path / "repositories.yaml"
    config.write_text(yaml.safe_dump({"repositories": {"../escape": {}}}))
    monkeypatch.setattr(main, "CONFIG", config)

    with pytest.raises(ValueError, match="repository alias"):
        main.repositories()
