"""Synchronize read-only repository snapshots for agent code tools."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

import yaml

CONFIG = Path(os.getenv("CODE_SYNC_CONFIG", "/app/config/repositories.yaml"))
DATA = Path(os.getenv("CODE_SYNC_DATA", "/app/data/code"))
INTERVAL = max(int(os.getenv("CODE_SYNC_INTERVAL_SECONDS", "300")), 60)
GITHUB_TOKEN_FILE = Path(os.getenv("GITHUB_TOKEN_FILE", "/run/secrets/github-read-token"))
REPOSITORY_ALIAS = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")


def git_env() -> dict[str, str]:
    """Handle git env."""
    return {
        **os.environ,
        "GIT_ASKPASS": "/usr/local/bin/open-agent-workspace-git-askpass",
        "GIT_TERMINAL_PROMPT": "0",
    }


def run(*args: str, env: dict[str, str] | None = None) -> str:
    """Run the requested data."""
    process = subprocess.run(
        args,
        check=False,
        capture_output=True,
        text=True,
        timeout=300,
        env=env,
    )
    if process.returncode:
        raise RuntimeError(process.stderr.strip()[:2_000] or "Git command failed")
    return process.stdout.strip()


def write_state(repo_dir: Path, payload: dict[str, object]) -> None:
    """Write state."""
    temporary = repo_dir / "state.json.tmp"
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    temporary.replace(repo_dir / "state.json")


def require_remote_credential(url: str) -> None:
    """Validate remote credential."""
    if not url.startswith("https://github.com/"):
        return
    if not GITHUB_TOKEN_FILE.is_file() or not GITHUB_TOKEN_FILE.read_text().strip():
        raise RuntimeError("GitHub read token is not configured")


def sync_repository(alias: str, config: dict[str, str]) -> dict[str, object]:
    """Handle sync repository."""
    repo_dir = DATA / alias
    mirror = repo_dir / "mirror.git"
    snapshots = repo_dir / "snapshots"
    repo_dir.mkdir(parents=True, exist_ok=True)
    snapshots.mkdir(exist_ok=True)
    branch = config["branch"]
    url = config["url"]
    require_remote_credential(url)

    if not mirror.exists():
        run("git", "clone", "--mirror", url, str(mirror), env=git_env())
        run("git", f"--git-dir={mirror}", "remote", "set-url", "origin", url)
    run(
        "git",
        f"--git-dir={mirror}",
        "fetch",
        "--prune",
        "origin",
        f"+refs/heads/{branch}:refs/heads/{branch}",
        env=git_env(),
    )
    commit = run("git", f"--git-dir={mirror}", "rev-parse", f"refs/heads/{branch}")
    snapshot = snapshots / commit
    if not snapshot.exists():
        temporary = snapshots / f".{commit}.tmp"
        shutil.rmtree(temporary, ignore_errors=True)
        run("git", "clone", "--no-checkout", "--shared", str(mirror), str(temporary))
        run("git", "-C", str(temporary), "checkout", "--detach", commit)
        temporary.rename(snapshot)

    current = repo_dir / "current"
    old_target = current.resolve() if current.is_symlink() else None
    new_link = repo_dir / ".current.tmp"
    new_link.unlink(missing_ok=True)
    new_link.symlink_to(snapshot.relative_to(repo_dir))
    new_link.replace(current)
    if old_target and old_target != snapshot and old_target.exists():
        previous = repo_dir / "previous"
        previous_tmp = repo_dir / ".previous.tmp"
        previous_tmp.unlink(missing_ok=True)
        previous_tmp.symlink_to(old_target.relative_to(repo_dir))
        previous_tmp.replace(previous)

    keep = {snapshot.resolve()}
    previous = repo_dir / "previous"
    if previous.is_symlink():
        keep.add(previous.resolve())
    for candidate in snapshots.iterdir():
        if candidate.is_dir() and candidate.resolve() not in keep:
            shutil.rmtree(candidate)

    state = {
        "repository": alias,
        "branch": branch,
        "current_commit": commit,
        "synced_at": datetime.now(UTC).isoformat(),
        "status": "ok",
    }
    write_state(repo_dir, state)
    return state


def repositories() -> dict[str, dict[str, str]]:
    """Load configured repositories and validate filesystem-safe aliases."""
    payload = yaml.safe_load(CONFIG.read_text()) or {}
    value = payload.get("repositories", {})
    if not isinstance(value, dict):
        raise TypeError("repositories.yaml must contain a repositories mapping")
    if any(not isinstance(alias, str) or not REPOSITORY_ALIAS.fullmatch(alias) for alias in value):
        raise ValueError("repositories.yaml contains an invalid repository alias")
    return value


def sync_all() -> int:
    """Handle sync all."""
    result = 0
    for alias, config in repositories().items():
        try:
            state = sync_repository(alias, config)
            print(json.dumps(state, sort_keys=True))
        except Exception as exc:  # noqa: BLE001 - daemon must retain the last good snapshot
            result = 1
            repo_dir = DATA / alias
            repo_dir.mkdir(parents=True, exist_ok=True)
            state_path = repo_dir / "state.json"
            previous = json.loads(state_path.read_text()) if state_path.exists() else {}
            previous.update(
                {
                    "repository": alias,
                    "last_error_at": datetime.now(UTC).isoformat(),
                    "last_error": str(exc)[:1_000],
                    "status": "stale",
                }
            )
            write_state(repo_dir, previous)
            print(json.dumps(previous, sort_keys=True))
    return result


def status() -> int:
    """Handle status."""
    for alias in repositories():
        path = DATA / alias / "state.json"
        value = json.loads(path.read_text()) if path.exists() else {"repository": alias, "status": "missing"}
        print(json.dumps(value, sort_keys=True))
    return 0


def main() -> None:
    """Run the command-line entry point."""
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["daemon", "once", "status"], nargs="?", default="daemon")
    args = parser.parse_args()
    if args.command == "once":
        raise SystemExit(sync_all())
    if args.command == "status":
        raise SystemExit(status())
    while True:
        sync_all()
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
