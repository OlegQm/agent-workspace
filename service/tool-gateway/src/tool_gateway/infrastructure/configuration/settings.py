"""Define role-scoped Tool Gateway configuration and credentials."""

import os
import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from tool_gateway.infrastructure.configuration.models import Manifest

ROLE_NAME = re.compile(r"^[a-z][a-z0-9_-]{1,31}$")


class Settings(BaseSettings):
    """Define Settings configuration values."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    gateway_role: str
    gateway_port: int
    gateway_host: str = "127.0.0.1"
    gateway_token_env: str
    gateway_max_request_body_bytes: int = Field(default=2_097_152, ge=65_536, le=16_777_216)
    agent_config_dir: Path = Path("/app/config/agents")
    agent_data_dir: Path = Path("/app/data/agents")
    source_credentials_file: Path | None = None
    code_data_dir: Path = Path("/app/data/code")
    code_config_file: Path = Path("/app/config/repositories.yaml")
    audit_log_dir: Path = Path("/app/data/audit")
    tool_result_max_rows: int = 10_000
    tool_export_max_rows: int = 250_000
    tool_export_max_bytes: int = 262_144_000
    bigquery_max_bytes_billed: int = 1_073_741_824
    google_cloud_project: str = "example-analytics-project"
    google_application_credentials: str | None = None
    metabase_url: str = "https://metabase.example.invalid"
    superfaktura_api_url: str = "https://moja.superfaktura.sk"
    meta_graph_api_version: str = "v23.0"

    @field_validator("gateway_role")
    @classmethod
    def validate_gateway_role(cls, value: str) -> str:
        """Prevent manifest and workspace path traversal through the role name."""
        if not ROLE_NAME.fullmatch(value):
            raise ValueError("GATEWAY_ROLE must be an identifier")
        return value

    @field_validator("gateway_host")
    @classmethod
    def validate_gateway_host(cls, value: str) -> str:
        """Keep the credential-bearing MCP gateway on loopback only."""
        if value not in {"127.0.0.1", "::1", "localhost"}:
            raise ValueError("GATEWAY_HOST must be a loopback address")
        return value

    @field_validator("meta_graph_api_version")
    @classmethod
    def validate_meta_version(cls, value: str) -> str:
        """Accept only explicit Meta Graph API version identifiers."""
        if not value.startswith("v") or not value[1:].replace(".", "").isdigit():
            raise ValueError("META_GRAPH_API_VERSION must look like v23.0")
        return value

    @property
    def token(self) -> str:
        """Return the configured token."""
        token = os.getenv(self.gateway_token_env)
        if not token:
            raise RuntimeError(f"{self.gateway_token_env} is required")
        if len(token) < 32:
            raise RuntimeError(f"{self.gateway_token_env} must contain at least 32 characters")
        return token

    @property
    def manifest(self) -> Manifest:
        """Return the configured manifest."""
        path = self.agent_config_dir / f"{self.gateway_role}.yaml"
        return Manifest.model_validate(yaml.safe_load(path.read_text()))

    @property
    def workspace(self) -> Path:
        """Return the configured workspace."""
        return (self.agent_data_dir / self.gateway_role / "workspace").resolve()

    @property
    def allowed_bigquery_datasets(self) -> list[str]:
        """Return the configured allowed BigQuery datasets."""
        return sorted(set(self.manifest.resources.bigquery_datasets))

    @property
    def allowed_metabase_database_ids(self) -> list[int]:
        """Return the configured allowed Metabase database IDs."""
        return sorted(set(self.manifest.resources.metabase_database_ids))

    @property
    def allowed_google_ads_customer_ids(self) -> list[str]:
        """Return the configured allowed google ads customer IDs."""
        return sorted(
            {
                item.replace("-", "")
                for item in self.manifest.resources.google_ads_customer_ids
                if item
            }
        )

    @property
    def allowed_meta_ad_account_ids(self) -> list[str]:
        """Return the configured allowed meta ad account IDs."""
        return sorted(
            {
                item.removeprefix("act_")
                for item in self.manifest.resources.meta_ad_account_ids
                if item
            }
        )

    @property
    def source_credentials(self) -> dict[str, Any]:
        """Return the configured source credentials."""
        if not self.source_credentials_file or not self.source_credentials_file.exists():
            return {}
        value = yaml.safe_load(self.source_credentials_file.read_text()) or {}
        if not isinstance(value, dict):
            raise TypeError("SOURCE_CREDENTIALS_FILE must contain a mapping")
        return value

    def credential(self, source: str, alias: str) -> dict[str, Any]:
        """Handle credential."""
        value = self.source_credentials.get(source, {}).get(alias)
        if value is None:
            raise RuntimeError(f"Credentials for {source}/{alias} are not configured")
        if not isinstance(value, dict):
            raise TypeError(f"Credentials for {source}/{alias} must be a mapping")
        return value

    def optional_credential(self, source: str, alias: str = "default") -> dict[str, Any]:
        """Handle optional credential."""
        value = self.source_credentials.get(source, {}).get(alias)
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise TypeError(f"Credentials for {source}/{alias} must be a mapping")
        return value

    def export_max_rows(self, source: str) -> int:
        """Export max rows."""
        configured = self.manifest.resources.tool_export_limits.get(source)
        if configured and configured.max_rows:
            return configured.max_rows
        return self.tool_export_max_rows

    def export_max_bytes(self, source: str) -> int:
        """Export max bytes."""
        configured = self.manifest.resources.tool_export_limits.get(source)
        if configured and configured.max_bytes:
            return configured.max_bytes
        return self.tool_export_max_bytes
