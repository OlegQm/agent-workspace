"""Define backend configuration loaded from the environment."""

from pathlib import Path
from urllib.parse import urlsplit

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Define Settings configuration values."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    app_base_url: str = "http://localhost"
    app_secret_key: str
    database_url: str
    session_cookie_secure: bool = False
    session_ttl_hours: int = 168
    session_refresh_interval_seconds: int = 300
    agent_config_dir: Path = Path("/app/config/agents")
    agent_data_dir: Path = Path("/app/data/agents")
    preview_cache_dir: Path = Path("/app/data/agents/.preview-cache")
    preview_cache_max_bytes: int = 2_147_483_648
    preview_cache_max_age_seconds: int = 604_800
    max_upload_bytes: int = 262_144_000
    max_workspace_bytes: int = 10_737_418_240
    max_request_body_bytes: int = 1_048_576
    metabase_planning_metabase_links_enabled: bool = False
    metabase_public_url: str | None = None
    metabase_planning_youtrack_enabled: bool = False
    youtrack_base_url: str | None = None
    youtrack_token: SecretStr | None = None
    youtrack_project_id: str | None = None
    youtrack_assignee_id: str | None = None
    youtrack_assignee_field_id: str | None = None

    @field_validator("app_env")
    @classmethod
    def validate_environment(cls, value: str) -> str:
        """Normalize and validate the application environment name."""
        normalized = value.strip().lower()
        if normalized not in {"development", "test", "production"}:
            raise ValueError("APP_ENV must be development, test, or production")
        return normalized

    @field_validator("app_base_url")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        """Require a simple HTTP origin without credentials, query, or path."""
        normalized = value.rstrip("/")
        parsed = urlsplit(normalized)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
        ):
            raise ValueError("APP_BASE_URL must be a plain HTTP(S) origin")
        return normalized

    @model_validator(mode="after")
    def validate_security_configuration(self) -> "Settings":
        """Reject weak production secrets and invalid request size limits."""
        if self.app_env == "production" and len(self.app_secret_key) < 32:
            raise ValueError("APP_SECRET_KEY must contain at least 32 characters in production")
        if self.max_request_body_bytes < 131_072:
            raise ValueError("MAX_REQUEST_BODY_BYTES must be at least 131072")
        if self.max_upload_bytes < self.max_request_body_bytes:
            raise ValueError("MAX_UPLOAD_BYTES must not be smaller than MAX_REQUEST_BODY_BYTES")
        if self.metabase_planning_metabase_links_enabled and not self.metabase_links_configured:
            raise ValueError("Metabase planning links require a secure public Metabase origin")
        if self.metabase_planning_youtrack_enabled and not self.youtrack_review_configured:
            raise ValueError("Metabase planning review requires complete YouTrack configuration")
        return self

    @staticmethod
    def _secure_origin(value: str | None) -> bool:
        """Return whether a value is an HTTPS origin without credentials or path."""
        if not value:
            return False
        parsed = urlsplit(value.rstrip("/"))
        return bool(
            parsed.scheme == "https"
            and parsed.hostname
            and not parsed.username
            and not parsed.password
            and not parsed.query
            and not parsed.fragment
            and parsed.path in {"", "/"}
        )

    @property
    def metabase_links_configured(self) -> bool:
        """Return whether secure Metabase navigation is explicitly enabled."""
        return self.metabase_planning_metabase_links_enabled and self._secure_origin(
            self.metabase_public_url
        )

    @property
    def youtrack_review_configured(self) -> bool:
        """Return whether every fail-closed YouTrack review setting is available."""
        identifiers = (
            self.youtrack_project_id,
            self.youtrack_assignee_id,
            self.youtrack_assignee_field_id,
        )
        token = self.youtrack_token.get_secret_value() if self.youtrack_token else ""
        return bool(
            self.metabase_planning_youtrack_enabled
            and self._secure_origin(self.youtrack_base_url)
            and token
            and all(value and value.strip() for value in identifiers)
        )

    @property
    def allowed_origins(self) -> set[str]:
        """Return the configured allowed origins."""
        return {self.app_base_url.rstrip("/")}

    @property
    def allowed_hosts(self) -> set[str]:
        """Return external and loopback host names accepted by the backend."""
        hostname = urlsplit(self.app_base_url).hostname
        if not hostname:
            raise RuntimeError("APP_BASE_URL has no hostname")
        return {hostname, "localhost", "127.0.0.1", "[::1]"}


settings = Settings()  # type: ignore[call-arg]
