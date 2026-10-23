#!/usr/bin/env python3
"""Render validated runtime secret files from Base64 values stored in .env."""

from __future__ import annotations

import argparse
import base64
import binascii
import json
import os
import tempfile
from pathlib import Path

import yaml

SECRET_FILES = {
    "ASSISTANT_SOURCES_YAML_B64": "assistant-sources.yaml",
    "GOOGLE_SERVICE_ACCOUNT_JSON_B64": "google-service-account.json",
    "GITHUB_READ_TOKEN_B64": "github-read-token",
}

REDUNDANT_RESOURCE_OVERRIDES = {
    "ASSISTANT_BIGQUERY_DATASETS",
    "METABASE_ASSISTANT_DATABASE_IDS",
    "ASSISTANT_GOOGLE_ANALYTICS_PROPERTY_IDS",
    "ASSISTANT_GOOGLE_ADS_CUSTOMER_IDS",
    "ASSISTANT_META_AD_ACCOUNT_IDS",
}


def dotenv(path: Path) -> dict[str, str]:
    """Handle dotenv."""
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def decode(value: str, variable: str) -> bytes:
    """Decode the requested data."""
    if not value:
        raise ValueError(f"{variable} is required")
    try:
        return base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError(f"{variable} is not valid Base64") from exc


def validate(variable: str, content: bytes) -> None:
    """Validate the requested data."""
    if variable == "ASSISTANT_SOURCES_YAML_B64":
        value = yaml.safe_load(content) or {}
        if not isinstance(value, dict) or not value:
            raise ValueError(f"{variable} must contain a non-empty YAML mapping")
    elif variable == "GOOGLE_SERVICE_ACCOUNT_JSON_B64":
        value = json.loads(content)
        required = {"project_id", "private_key", "client_email", "token_uri"}
        if (
            not isinstance(value, dict)
            or value.get("type") != "service_account"
            or not required.issubset(value)
            or value.get("token_uri") != "https://oauth2.googleapis.com/token"
        ):
            raise ValueError(f"{variable} must contain a service-account JSON")
    elif not content.strip():
        raise ValueError(f"{variable} must not be empty")


def atomic_write(path: Path, content: bytes) -> None:
    """Handle atomic write."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def render(env_path: Path, output_dir: Path) -> None:
    """Render the requested data."""
    values = dotenv(env_path)
    for variable, filename in SECRET_FILES.items():
        content = decode(values.get(variable, ""), variable)
        validate(variable, content)
        atomic_write(output_dir / filename, content)
    output_dir.chmod(0o700)


def update_env(path: Path, replacements: dict[str, str]) -> None:
    """Update env."""
    lines = path.read_text().splitlines() if path.exists() else []
    retained = [
        line
        for line in lines
        if line.split("=", 1)[0].strip() not in replacements or "=" not in line
    ]
    if retained and retained[-1]:
        retained.append("")
    retained.extend(f"{key}={value}" for key, value in replacements.items())
    atomic_write(path, ("\n".join(retained).rstrip() + "\n").encode())


def capture(env_path: Path, source_dir: Path) -> None:
    """Capture the requested data."""
    replacements: dict[str, str] = {}
    for variable, filename in SECRET_FILES.items():
        path = source_dir / filename
        if not path.is_file():
            raise FileNotFoundError(f"Missing secret source file: {filename}")
        content = path.read_bytes()
        validate(variable, content)
        replacements[variable] = base64.b64encode(content).decode("ascii")
    update_env(env_path, replacements)


def prune(env_path: Path) -> None:
    """Remove stale the requested data."""
    lines = env_path.read_text().splitlines() if env_path.exists() else []
    retained = [
        line
        for line in lines
        if "=" not in line
        or line.split("=", 1)[0].strip() not in REDUNDANT_RESOURCE_OVERRIDES
    ]
    atomic_write(env_path, ("\n".join(retained).rstrip() + "\n").encode())


def main() -> None:
    """Run the command-line entry point."""
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("render", "capture", "prune"))
    parser.add_argument("--env", type=Path, default=Path(".env"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/runtime-secrets"))
    parser.add_argument("--source-dir", type=Path, default=Path("secrets"))
    args = parser.parse_args()

    if args.command == "render":
        render(args.env, args.output_dir)
        print("Runtime secrets rendered")
    elif args.command == "capture":
        capture(args.env, args.source_dir)
        print("Secrets captured into .env")
    else:
        prune(args.env)
        print("Redundant resource overrides removed")


if __name__ == "__main__":
    main()
