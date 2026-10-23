"""Define validated agent configuration models."""

import os
import re
from pathlib import Path

from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator

from features.agents.infrastructure.configuration.llm import LLMProfile
from infrastructure.settings import settings

IDENTIFIER = re.compile(r"^[a-z][a-z0-9_-]{1,31}$")


class AgentResources(BaseModel):
    """Describe external resources available to an agent."""

    environment: str = "prod"
    metabase_scope: str | None = None
    metabase_collection_ids: list[int] = Field(default_factory=list)
    metabase_database_ids: list[int] = Field(default_factory=list)
    bigquery_datasets: list[str] = Field(default_factory=list)
    google_ads_customer_ids: list[str] = Field(default_factory=list)
    meta_ad_account_ids: list[str] = Field(default_factory=list)
    google_analytics_property_ids: list[str] = Field(default_factory=list)


class AgentConfig(BaseModel):
    """Describe one validated agent runtime configuration."""

    id: str
    display_name: str
    username: str
    sandbox_name: str
    hermes_url: HttpUrl
    hermes_api_key_env: str
    host_port: int
    tool_gateway_port: int
    tool_gateway_token_env: str
    workspace_subdir: str = "workspace"
    locale: str = "en"
    tools: list[str]
    resources: AgentResources
    llm: LLMProfile

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        """Validate the stable agent identifier."""
        if not IDENTIFIER.fullmatch(value):
            raise ValueError("invalid agent id")
        return value

    @field_validator("workspace_subdir")
    @classmethod
    def validate_workspace_subdir(cls, value: str) -> str:
        """Require a single relative workspace directory name."""
        if value in {"", ".", ".."} or Path(value).name != value:
            raise ValueError("workspace_subdir must be one relative directory name")
        return value

    @model_validator(mode="after")
    def validate_internal_runtime(self) -> "AgentConfig":
        """Keep Hermes endpoints on the configured loopback port."""
        host = self.hermes_url.host
        if host not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("Hermes URL must use loopback")
        if self.hermes_url.scheme != "http" or self.hermes_url.port != self.host_port:
            raise ValueError("Hermes URL must use HTTP on host_port")
        return self

    @property
    def hermes_api_key(self) -> str:
        """Return the configured Hermes API key."""
        value = os.getenv(self.hermes_api_key_env)
        if not value:
            raise RuntimeError(f"{self.hermes_api_key_env} is not configured")
        return value

    @property
    def workspace_root(self) -> Path:
        """Return the configured workspace root."""
        return (settings.agent_data_dir / self.id / self.workspace_subdir).resolve()

    @property
    def instructions(self) -> str:
        """Load the current role instructions injected into every Hermes turn."""
        path = settings.agent_config_dir / "prompts" / self.id / "SOUL.md"
        try:
            content = path.read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise RuntimeError(f"Agent instructions are unavailable: {path}") from exc
        if not content:
            raise RuntimeError(f"Agent instructions are empty: {path}")
        return content

    @property
    def metabase_planner_instructions(self) -> str:
        """Load the dedicated structured Metabase requirements-planning instructions."""
        path = settings.agent_config_dir / "prompts" / self.id / "METABASE_PLANNER.md"
        try:
            content = path.read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise RuntimeError(f"Metabase planner instructions are unavailable: {path}") from exc
        if not content:
            raise RuntimeError(f"Metabase planner instructions are empty: {path}")
        return content
