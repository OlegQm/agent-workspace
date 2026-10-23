"""Characterize all read-only code repository operations."""

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from tool_gateway.infrastructure.configuration.settings import Settings
from tool_gateway.integrations.code.infrastructure import client as module
from tool_gateway.integrations.code.infrastructure.client import SAFE_HISTORY_PATHS, CodeClient

settings = Settings()


def configure_code(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    repositories: list[str] | None = None,
) -> tuple[Path, Path]:
    """Configure one isolated synchronized repository."""
    config = tmp_path / "repositories.yaml"
    config.write_text(
        yaml.safe_dump(
            {
                "repositories": {
                    "backend": {"branch": "main", "url": "https://example.test/backend.git"},
                    "missing": {"branch": "main", "url": "https://example.test/missing.git"},
                }
            }
        )
    )
    data = tmp_path / "code"
    monkeypatch.setattr(settings, "code_config_file", config)
    monkeypatch.setattr(settings, "code_data_dir", data)
    resources = SimpleNamespace(code_repositories=repositories or ["backend"])
    monkeypatch.setattr(
        Settings,
        "manifest",
        property(lambda _self: SimpleNamespace(resources=resources)),
    )
    return config, data


def create_repository(data: Path) -> tuple[Path, str, str]:
    """Create a bare mirror with two commits and representative files."""
    work = data.parent / "work"
    mirror = data / "backend/mirror.git"
    work.mkdir(parents=True)
    mirror.parent.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=work, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=work, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=work, check=True)
    (work / "app.py").write_text("API_KEY=first-secret\nprint('first')\n")
    (work / ".env").write_text("PASSWORD=hidden\n")
    subprocess.run(["git", "add", "."], cwd=work, check=True)
    subprocess.run(["git", "commit", "-qm", "first"], cwd=work, check=True)
    first = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=work, text=True).strip()
    (work / "app.py").write_text("API_KEY=second-secret\nprint('second')\n")
    subprocess.run(["git", "add", "app.py"], cwd=work, check=True)
    subprocess.run(["git", "commit", "-qm", "second"], cwd=work, check=True)
    second = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=work, text=True).strip()
    subprocess.run(["git", "clone", "-q", "--bare", str(work), str(mirror)], check=True)
    return mirror, first, second


def test_repository_configuration_failures(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Characterize missing, malformed, unconfigured, and unsynchronized repositories."""
    adapter = CodeClient(settings)
    config, data = configure_code(tmp_path, monkeypatch, ["backend", "unknown", "missing"])
    config.unlink()
    with pytest.raises(RuntimeError, match="not mounted"):
        adapter._repositories()
    config.write_text("repositories: []\n")
    with pytest.raises(TypeError, match="repositories mapping"):
        adapter._repositories()
    config.write_text(yaml.safe_dump({"repositories": {"backend": "invalid"}}))
    with pytest.raises(TypeError, match="not configured"):
        adapter._repository("backend")
    config.write_text(yaml.safe_dump({"repositories": {"backend": {"branch": "main"}}}))
    with pytest.raises(RuntimeError, match="not been synchronized"):
        adapter._repository("backend")
    with pytest.raises(ValueError, match="not allowed"):
        adapter._repository("outside")
    assert not data.exists()


def test_git_runner_failure_size_and_binary(monkeypatch: pytest.MonkeyPatch) -> None:
    """Characterize subprocess failures and output safety limits."""

    def result(returncode: int, stdout: bytes = b"", stderr: bytes = b""):
        """Build a subprocess result double."""
        return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)

    monkeypatch.setattr(module.subprocess, "run", lambda *args, **kwargs: result(1, stderr=b"bad"))
    with pytest.raises(ValueError, match="Git read failed: bad"):
        CodeClient._run("mirror", "status")
    monkeypatch.setattr(module.subprocess, "run", lambda *args, **kwargs: result(0, b"large"))
    with pytest.raises(ValueError, match="size limit"):
        CodeClient._run("mirror", "status", max_bytes=2)
    monkeypatch.setattr(module.subprocess, "run", lambda *args, **kwargs: result(0, b"a\0b"))
    with pytest.raises(ValueError, match="Binary"):
        CodeClient._run("mirror", "status")
    monkeypatch.setattr(module.subprocess, "run", lambda *args, **kwargs: result(0, b"text"))
    assert CodeClient._run("mirror", "status") == "text"


def test_all_repository_read_operations(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Exercise repository listing, history, content, search, blame, and diff."""
    _, data = configure_code(tmp_path, monkeypatch, ["backend", "missing"])
    _, first, second = create_repository(data)
    state_path = data / "backend/state.json"
    state_path.write_text(json.dumps({"status": "ready", "current_commit": second}))
    adapter = CodeClient(settings)

    repositories = adapter.list_repositories()
    assert repositories[0]["status"] == "ready"
    assert repositories[1]["status"] == "not_synchronized"
    assert adapter.status("backend")["current_commit"] == second
    state_path.unlink()
    assert adapter.status("backend") == {"status": "unknown"}

    tree = adapter.list_tree("backend")
    assert tree["commit"] == second
    assert [item["path"] for item in tree["items"]] == ["app.py"]
    assert adapter.list_tree("backend", "app.py", first)["commit"] == first

    content = adapter.read_file("backend", "app.py")
    assert "second-secret" not in content["content"]
    assert "[REDACTED]" in content["content"]
    matches = adapter.search("backend", "second", "app.py")
    assert matches["matches"] and matches["truncated"] is False
    assert adapter.search("backend", "absent")["matches"] == []
    assert adapter.log("backend", 500)["items"][0]["commit"] == second
    assert adapter.log("backend", 0)["items"]
    assert adapter.show_commit("backend", first)["commit"] == first
    assert adapter.blame("backend", "app.py")["path"] == "app.py"
    diff = adapter.diff("backend", first, second)
    assert diff["from_commit"] == first and diff["to_commit"] == second
    assert "second-secret" not in diff["content"]


def test_repository_input_and_reachability_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Characterize search bounds, path filtering, and unreachable commits."""
    _, data = configure_code(tmp_path, monkeypatch)
    create_repository(data)
    adapter = CodeClient(settings)
    for query in ("", "x" * 201):
        with pytest.raises(ValueError, match="1-200"):
            adapter.search("backend", query)

    original_run = module.subprocess.run

    def reject_ancestor(args, **kwargs):
        """Reject only the merge-base reachability check."""
        if "merge-base" in args:
            return SimpleNamespace(returncode=1, stdout=b"", stderr=b"")
        return original_run(args, **kwargs)

    monkeypatch.setattr(module.subprocess, "run", reject_ancestor)
    with pytest.raises(ValueError, match="not reachable"):
        adapter.read_file("backend", "app.py")


def test_search_propagates_fatal_errors_and_filters_secret_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Characterize fatal grep failures and secret-path result filtering."""
    adapter = CodeClient(settings)
    monkeypatch.setattr(adapter, "_commit", lambda *_args: ("abc", "mirror", {}))

    monkeypatch.setattr(
        adapter,
        "_run",
        lambda *_args: (_ for _ in ()).throw(ValueError("Git read failed: fatal: invalid")),
    )
    with pytest.raises(ValueError, match="fatal"):
        adapter.search("backend", "needle")

    monkeypatch.setattr(
        adapter,
        "_run",
        lambda *_args: "abc:.env:1:needle\nabc:src/app.py:2:needle",
    )
    assert adapter.search("backend", "needle")["matches"] == ["src/app.py:2:needle"]


@pytest.mark.parametrize(
    "path",
    ["../secret", "/etc/passwd", ".env", ".env.production", "keys/private.pem"],
)
def test_paths_block_secrets_and_workspace_escape(path: str) -> None:
    """Reject secret paths and paths outside a repository."""
    with pytest.raises(ValueError):
        CodeClient._path(path)


def test_redaction_and_history_path_policy() -> None:
    """Redact common assignments while preserving safe paths and history."""
    value = CodeClient._redact(
        'API_KEY=abc PASSWORD: xyz "client_secret": "json-secret" normal=value'
    )
    assert "abc" not in value
    assert "xyz" not in value
    assert "json-secret" not in value
    assert "normal=value" in value
    assert CodeClient._path(".github/workflows/test.yml") == ".github/workflows/test.yml"
    assert ":(exclude,glob)**/.env*" in SAFE_HISTORY_PATHS
    assert ":(exclude,glob)**/secrets/**" in SAFE_HISTORY_PATHS
    assert ":(exclude,glob)**/*.pem" in SAFE_HISTORY_PATHS


def test_history_path_policy_hides_secret_changes(tmp_path: Path) -> None:
    """Exclude secret files from history output."""
    repository = tmp_path / "repository"
    repository.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repository, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repository,
        check=True,
    )
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repository, check=True)
    (repository / "app.py").write_text("print('safe')\n")
    (repository / ".env").write_text("PASSWORD=secret\n")
    subprocess.run(["git", "add", "."], cwd=repository, check=True)
    subprocess.run(["git", "commit", "-qm", "initial"], cwd=repository, check=True)

    output = subprocess.run(
        ["git", "show", "--stat", "HEAD", *SAFE_HISTORY_PATHS],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout

    assert "app.py" in output
    assert ".env" not in output
    assert "secret" not in output
