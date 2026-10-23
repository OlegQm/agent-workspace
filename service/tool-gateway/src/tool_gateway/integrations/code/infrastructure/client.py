"""Provide the read-only repository code adapter."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import PurePosixPath
from typing import Any

import yaml

from tool_gateway.infrastructure.configuration.settings import Settings
from tool_gateway.infrastructure.security.resources import require_allowed_exact

SECRET_PATH_PARTS = {
    ".env",
    ".npmrc",
    ".pypirc",
    ".netrc",
    "credentials",
    "secrets",
    "id_rsa",
    "id_ed25519",
}
SECRET_VALUE_RE = re.compile(
    r"(?i)([\"']?(?:api[_-]?key|access[_-]?token|refresh[_-]?token|"
    r"client[_-]?secret|password)[\"']?\s*[:=]\s*)([\"']?)([^\"'\s,;}]+)"
)
SAFE_HISTORY_PATHS = (
    "--",
    ".",
    ":(exclude,glob)**/.env*",
    ":(exclude,glob)**/.npmrc",
    ":(exclude,glob)**/.pypirc",
    ":(exclude,glob)**/.netrc",
    ":(exclude,glob)**/credentials/**",
    ":(exclude,glob)**/secrets/**",
    ":(exclude,glob)**/id_rsa",
    ":(exclude,glob)**/id_ed25519",
    ":(exclude,glob)**/*.pem",
    ":(exclude,glob)**/*.key",
    ":(exclude,glob)**/*.p12",
    ":(exclude,glob)**/*.pfx",
)


class CodeClient:
    """Provide read-only operations for Code."""

    def __init__(self, settings: Settings) -> None:
        """Initialize the client with its role-scoped configuration."""
        self.settings = settings

    def _repositories(self) -> dict[str, dict[str, Any]]:
        """Handle internal repositories details."""
        if not self.settings.code_config_file.exists():
            raise RuntimeError("Code repository configuration is not mounted")
        payload = yaml.safe_load(self.settings.code_config_file.read_text()) or {}
        repositories = payload.get("repositories", {})
        if not isinstance(repositories, dict):
            raise TypeError("repositories.yaml must contain a repositories mapping")
        return repositories

    def _repository(self, alias: str) -> tuple[dict[str, Any], str]:
        """Handle internal repository details."""
        require_allowed_exact(
            alias, self.settings.manifest.resources.code_repositories, "Code repository"
        )
        config = self._repositories().get(alias)
        if not isinstance(config, dict):
            raise TypeError(f"Code repository {alias} is not configured")
        mirror = self.settings.code_data_dir / alias / "mirror.git"
        if not mirror.is_dir():
            raise RuntimeError(f"Code repository {alias} has not been synchronized")
        return config, str(mirror)

    @staticmethod
    def _run(mirror: str, *args: str, max_bytes: int = 2_000_000) -> str:
        """Run the requested data."""
        process = subprocess.run(
            ["git", f"--git-dir={mirror}", *args],
            check=False,
            capture_output=True,
            text=False,
            timeout=30,
        )
        if process.returncode:
            message = process.stderr.decode("utf-8", errors="replace")[:2_000]
            raise ValueError(f"Git read failed: {message}")
        if len(process.stdout) > max_bytes:
            raise ValueError("Code result exceeds the configured size limit")
        if b"\x00" in process.stdout:
            raise ValueError("Binary code content is not available")
        return process.stdout.decode("utf-8", errors="replace")

    @staticmethod
    def _path(path: str) -> str:
        """Handle internal path details."""
        parsed = PurePosixPath(path)
        if parsed.is_absolute() or ".." in parsed.parts:
            raise ValueError("Code path must be relative and cannot contain '..'")
        if any(
            part.lower() in SECRET_PATH_PARTS or part.lower().startswith(".env")
            for part in parsed.parts
        ):
            raise ValueError("Secret-bearing code paths are not available")
        if any(part.lower().endswith((".pem", ".key", ".p12", ".pfx")) for part in parsed.parts):
            raise ValueError("Key and credential files are not available")
        return parsed.as_posix()

    @staticmethod
    def _redact(value: str) -> str:
        """Handle internal redact details."""
        return SECRET_VALUE_RE.sub(
            lambda match: f"{match.group(1)}{match.group(2)}[REDACTED]",
            value,
        )

    def _commit(self, alias: str, revision: str | None) -> tuple[str, str, dict[str, Any]]:
        """Handle internal commit details."""
        config, mirror = self._repository(alias)
        branch = str(config["branch"])
        tip = self._run(mirror, "rev-parse", f"refs/heads/{branch}").strip()
        commit = (
            tip
            if not revision
            else self._run(mirror, "rev-parse", f"{revision}^{{commit}}").strip()
        )
        check = subprocess.run(
            ["git", f"--git-dir={mirror}", "merge-base", "--is-ancestor", commit, tip],
            check=False,
            capture_output=True,
            timeout=10,
        )
        if check.returncode:
            raise ValueError("Commit is not reachable from the configured default branch")
        return commit, mirror, config

    def list_repositories(self) -> list[dict[str, Any]]:
        """List repositories."""
        rows = []
        for alias in self.settings.manifest.resources.code_repositories:
            config = self._repositories().get(alias, {})
            state_path = self.settings.code_data_dir / alias / "state.json"
            state = json.loads(state_path.read_text()) if state_path.exists() else {}
            rows.append(
                {
                    "repository": alias,
                    "branch": config.get("branch"),
                    "current_commit": state.get("current_commit"),
                    "synced_at": state.get("synced_at"),
                    "status": state.get("status", "not_synchronized"),
                }
            )
        return rows

    def status(self, alias: str) -> dict[str, Any]:
        """Handle status."""
        self._repository(alias)
        state_path = self.settings.code_data_dir / alias / "state.json"
        return json.loads(state_path.read_text()) if state_path.exists() else {"status": "unknown"}

    def list_tree(self, alias: str, path: str = "", revision: str | None = None) -> dict[str, Any]:
        """List tree."""
        commit, mirror, _ = self._commit(alias, revision)
        safe_path = self._path(path) if path else ""
        args = ["ls-tree", "-l", commit]
        if safe_path:
            args.extend(["--", safe_path])
        output = self._run(mirror, *args)
        rows = []
        for line in output.splitlines():
            metadata, name = line.split("\t", 1)
            mode, object_type, sha, size = metadata.split()
            try:
                self._path(name)
            except ValueError:
                continue
            rows.append({"path": name, "type": object_type, "mode": mode, "sha": sha, "size": size})
        return {"commit": commit, "items": rows}

    def read_file(self, alias: str, path: str, revision: str | None = None) -> dict[str, Any]:
        """Read file."""
        commit, mirror, _ = self._commit(alias, revision)
        safe_path = self._path(path)
        content = self._run(mirror, "show", f"{commit}:{safe_path}")
        return {"commit": commit, "path": safe_path, "content": self._redact(content)}

    def search(
        self, alias: str, query: str, path: str = "", revision: str | None = None
    ) -> dict[str, Any]:
        """Search the requested data."""
        if not query or len(query) > 200:
            raise ValueError("Code search query must contain 1-200 characters")
        commit, mirror, _ = self._commit(alias, revision)
        safe_path = self._path(path) if path else ""
        args = ["grep", "-n", "-I", "--max-count=200", "-e", query, commit]
        if safe_path:
            args.extend(["--", safe_path])
        try:
            output = self._run(mirror, *args)
        except ValueError as exc:
            if "Git read failed:" in str(exc) and "fatal:" not in str(exc):
                output = ""
            else:
                raise
        lines = []
        for line in output.splitlines()[:500]:
            remainder = line.removeprefix(f"{commit}:")
            path_part = remainder.split(":", 1)[0]
            try:
                self._path(path_part)
            except ValueError:
                continue
            lines.append(self._redact(remainder))
        return {"commit": commit, "matches": lines, "truncated": len(lines) >= 500}

    def log(self, alias: str, limit: int = 50) -> dict[str, Any]:
        """Handle log."""
        commit, mirror, _ = self._commit(alias, None)
        count = min(max(limit, 1), 200)
        output = self._run(
            mirror,
            "log",
            f"-{count}",
            "--date=iso-strict",
            "--pretty=format:%H%x09%aI%x09%an%x09%s",
            commit,
        )
        rows = []
        for line in output.splitlines():
            sha, authored_at, author, subject = line.split("\t", 3)
            rows.append(
                {"commit": sha, "authored_at": authored_at, "author": author, "subject": subject}
            )
        return {"items": rows}

    def show_commit(self, alias: str, revision: str) -> dict[str, Any]:
        """Handle show commit."""
        commit, mirror, _ = self._commit(alias, revision)
        output = self._run(
            mirror,
            "show",
            "--stat",
            "--format=fuller",
            "--no-renames",
            commit,
            *SAFE_HISTORY_PATHS,
        )
        return {"commit": commit, "content": self._redact(output)}

    def blame(self, alias: str, path: str, revision: str | None = None) -> dict[str, Any]:
        """Handle blame."""
        commit, mirror, _ = self._commit(alias, revision)
        safe_path = self._path(path)
        output = self._run(mirror, "blame", "--date=short", commit, "--", safe_path)
        return {"commit": commit, "path": safe_path, "content": self._redact(output)}

    def diff(self, alias: str, from_revision: str, to_revision: str) -> dict[str, Any]:
        """Handle diff."""
        from_commit, mirror, _ = self._commit(alias, from_revision)
        to_commit, _, _ = self._commit(alias, to_revision)
        output = self._run(
            mirror,
            "diff",
            "--no-ext-diff",
            "--no-renames",
            from_commit,
            to_commit,
            *SAFE_HISTORY_PATHS,
        )
        return {
            "from_commit": from_commit,
            "to_commit": to_commit,
            "content": self._redact(output),
        }
