#!/usr/bin/env python3
"""Create a shell-safe production environment payload from GitHub Secrets."""

from __future__ import annotations

import base64
import os
import shlex
import sys
from pathlib import Path
from urllib.parse import quote

REQUIRED_SECRETS = (
    "APP_BASE_URL",
    "APP_SECRET_KEY",
    "POSTGRES_DB",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "HERMES_API_KEY_ASSISTANT",
    "TOOL_GATEWAY_TOKEN_ASSISTANT",
    "ASSISTANT_SOURCES_YAML_B64",
    "GOOGLE_SERVICE_ACCOUNT_JSON_B64",
    "CODE_SYNC_GITHUB_TOKEN_B64",
    "BACKEND_IMAGE",
    "FRONTEND_IMAGE",
    "TOOL_GATEWAY_IMAGE",
    "CODE_SYNC_IMAGE",
)

BASE64_SECRETS = (
    "ASSISTANT_SOURCES_YAML_B64",
    "GOOGLE_SERVICE_ACCOUNT_JSON_B64",
    "CODE_SYNC_GITHUB_TOKEN_B64",
)

ENABLED_VALUES = {"1", "true", "yes", "on"}


def optional_planning_environment() -> dict[str, str]:
    """Return validated opt-in planning integration settings."""
    values = {
        "METABASE_PLANNING_METABASE_LINKS_ENABLED": os.environ.get(
            "METABASE_PLANNING_METABASE_LINKS_ENABLED", "false"
        ),
        "METABASE_PUBLIC_URL": os.environ.get("METABASE_PUBLIC_URL", ""),
        "METABASE_PLANNING_YOUTRACK_ENABLED": os.environ.get(
            "METABASE_PLANNING_YOUTRACK_ENABLED", "false"
        ),
        "YOUTRACK_BASE_URL": os.environ.get("YOUTRACK_BASE_URL", ""),
        "YOUTRACK_TOKEN": os.environ.get("YOUTRACK_TOKEN", ""),
        "YOUTRACK_PROJECT_ID": os.environ.get("YOUTRACK_PROJECT_ID", ""),
        "YOUTRACK_ASSIGNEE_ID": os.environ.get("YOUTRACK_ASSIGNEE_ID", ""),
        "YOUTRACK_ASSIGNEE_FIELD_ID": os.environ.get("YOUTRACK_ASSIGNEE_FIELD_ID", ""),
    }
    metabase_enabled = values["METABASE_PLANNING_METABASE_LINKS_ENABLED"].lower() in ENABLED_VALUES
    youtrack_enabled = values["METABASE_PLANNING_YOUTRACK_ENABLED"].lower() in ENABLED_VALUES
    values["METABASE_PLANNING_METABASE_LINKS_ENABLED"] = str(metabase_enabled).lower()
    values["METABASE_PLANNING_YOUTRACK_ENABLED"] = str(youtrack_enabled).lower()
    if metabase_enabled and not values["METABASE_PUBLIC_URL"]:
        raise SystemExit("Enabled Metabase planning links require METABASE_PUBLIC_URL")
    youtrack_fields = (
        "YOUTRACK_BASE_URL",
        "YOUTRACK_TOKEN",
        "YOUTRACK_PROJECT_ID",
        "YOUTRACK_ASSIGNEE_ID",
        "YOUTRACK_ASSIGNEE_FIELD_ID",
    )
    if youtrack_enabled:
        missing = [key for key in youtrack_fields if not values[key]]
        if missing:
            raise SystemExit(
                "Enabled YouTrack planning review is missing: " + ", ".join(missing)
            )
    return values


def required_environment() -> dict[str, str]:
    """Return required non-empty environment values or terminate safely."""
    values = {key: os.environ.get(key, "") for key in REQUIRED_SECRETS}
    missing = [key for key, value in values.items() if not value]
    if missing:
        raise SystemExit(f"Missing required GitHub Secrets: {', '.join(missing)}")
    for key in BASE64_SECRETS:
        try:
            decoded = base64.b64decode(values[key], validate=True)
        except ValueError as exc:
            raise SystemExit(f"{key} is not valid Base64") from exc
        if not decoded:
            raise SystemExit(f"{key} decodes to an empty value")
    if len(values["APP_SECRET_KEY"]) < 32:
        raise SystemExit("APP_SECRET_KEY must contain at least 32 characters")
    return values


def runtime_values(values: dict[str, str]) -> dict[str, str]:
    """Build the complete production runtime and bootstrap environment."""
    database_url = (
        "postgresql+asyncpg://"
        f"{quote(values['POSTGRES_USER'], safe='')}:"
        f"{quote(values['POSTGRES_PASSWORD'], safe='')}@"
        "127.0.0.1:55432/"
        f"{quote(values['POSTGRES_DB'], safe='')}"
    )
    runtime = {
        "APP_ENV": "production",
        "APP_BASE_URL": values["APP_BASE_URL"].rstrip("/"),
        "APP_SECRET_KEY": values["APP_SECRET_KEY"],
        "POSTGRES_DB": values["POSTGRES_DB"],
        "POSTGRES_USER": values["POSTGRES_USER"],
        "POSTGRES_PASSWORD": values["POSTGRES_PASSWORD"],
        "DATABASE_URL": database_url,
        "SESSION_COOKIE_SECURE": "false",
        "SESSION_TTL_HOURS": "168",
        "SESSION_REFRESH_INTERVAL_SECONDS": "300",
        "AGENT_CONFIG_DIR": "/app/config/agents",
        "AGENT_DATA_DIR": "/app/data/agents",
        "PREVIEW_CACHE_DIR": "/app/data/agents/.preview-cache",
        "PREVIEW_CACHE_MAX_BYTES": "2147483648",
        "PREVIEW_CACHE_MAX_AGE_SECONDS": "604800",
        "MAX_UPLOAD_BYTES": "262144000",
        "MAX_WORKSPACE_BYTES": "10737418240",
        "MAX_REQUEST_BODY_BYTES": "1048576",
        "HERMES_API_KEY_ASSISTANT": values["HERMES_API_KEY_ASSISTANT"],
        "TOOL_GATEWAY_TOKEN_ASSISTANT": values["TOOL_GATEWAY_TOKEN_ASSISTANT"],
        "TOOL_RESULT_MAX_ROWS": "10000",
        "TOOL_EXPORT_MAX_ROWS": "250000",
        "TOOL_EXPORT_MAX_BYTES": "262144000",
        "GATEWAY_HOST": "127.0.0.1",
        "GATEWAY_MAX_REQUEST_BODY_BYTES": "2097152",
        "CODE_SYNC_INTERVAL_SECONDS": "300",
        "BIGQUERY_MAX_BYTES_BILLED": "1073741824",
        "METABASE_URL": "https://metabase.example.invalid",
        "SUPERFAKTURA_API_URL": "https://moja.superfaktura.sk",
        "GOOGLE_APPLICATION_CREDENTIALS": "/run/secrets/google-service-account.json",
        "GOOGLE_CLOUD_PROJECT": "example-analytics-project",
        "META_GRAPH_API_VERSION": "v23.0",
        "ASSISTANT_SOURCES_YAML_B64": values["ASSISTANT_SOURCES_YAML_B64"],
        "GOOGLE_SERVICE_ACCOUNT_JSON_B64": values["GOOGLE_SERVICE_ACCOUNT_JSON_B64"],
        "GITHUB_READ_TOKEN_B64": values["CODE_SYNC_GITHUB_TOKEN_B64"],
        "BACKEND_IMAGE": values["BACKEND_IMAGE"],
        "FRONTEND_IMAGE": values["FRONTEND_IMAGE"],
        "TOOL_GATEWAY_IMAGE": values["TOOL_GATEWAY_IMAGE"],
        "CODE_SYNC_IMAGE": values["CODE_SYNC_IMAGE"],
    }
    runtime.update(optional_planning_environment())
    return runtime


def write_environment(path: Path, values: dict[str, str]) -> None:
    """Atomically write a sourceable and Docker Compose compatible env file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        "\n".join(f"{key}={shlex.quote(value)}" for key, value in values.items()) + "\n"
    )
    temporary.chmod(0o600)
    temporary.replace(path)


def main() -> None:
    """Create the deployment payload at the requested path."""
    if len(sys.argv) != 2:
        raise SystemExit("Usage: create_runtime_env.py OUTPUT_PATH")
    write_environment(Path(sys.argv[1]), runtime_values(required_environment()))


if __name__ == "__main__":
    main()
