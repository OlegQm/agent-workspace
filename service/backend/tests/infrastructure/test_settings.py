"""Test application settings validation and derived allowlists."""

import pytest
from pydantic import ValidationError

from infrastructure.settings import Settings


@pytest.mark.unit
def test_settings_validation_and_allowlists() -> None:
    """Preserve accepted settings normalization and production rejection rules."""
    configured = Settings(
        _env_file=None,
        app_secret_key="x" * 32,
        database_url="postgresql+asyncpg://user:pass@localhost/db",
        app_env=" PRODUCTION ",
        app_base_url="https://example.test/",
    )
    assert configured.app_env == "production"
    assert configured.allowed_origins == {"https://example.test"}
    assert configured.allowed_hosts == {"example.test", "localhost", "127.0.0.1", "[::1]"}
    assert configured.metabase_links_configured is False
    assert configured.youtrack_review_configured is False
    with pytest.raises(ValidationError):
        Settings(_env_file=None, app_secret_key="short", database_url="x", app_env="production")
    with pytest.raises(ValidationError):
        Settings(_env_file=None, app_secret_key="x", database_url="x", app_base_url="https://a.test/path")
    with pytest.raises(ValidationError):
        Settings(_env_file=None, app_secret_key="x", database_url="x", max_request_body_bytes=1)
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            app_secret_key="x",
            database_url="x",
            max_request_body_bytes=200_000,
            max_upload_bytes=150_000,
        )
    with pytest.raises(ValidationError):
        Settings(_env_file=None, app_secret_key="x", database_url="x", app_env="unknown")


@pytest.mark.unit
def test_external_planning_integrations_are_explicit_and_fail_closed() -> None:
    """Enable external actions only with complete validated server configuration."""
    configured = Settings(
        _env_file=None,
        app_secret_key="x",
        database_url="x",
        metabase_planning_metabase_links_enabled=True,
        metabase_public_url="https://bi.example.test",
        metabase_planning_youtrack_enabled=True,
        youtrack_base_url="https://tracker.example.test",
        youtrack_token="secret",
        youtrack_project_id="0-1",
        youtrack_assignee_id="1-2",
        youtrack_assignee_field_id="3-4",
    )

    assert configured.metabase_links_configured is True
    assert configured.youtrack_review_configured is True
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            app_secret_key="x",
            database_url="x",
            metabase_planning_metabase_links_enabled=True,
            metabase_public_url="http://remote.example.test",
        )
    with pytest.raises(ValidationError, match="complete YouTrack"):
        Settings(
            _env_file=None,
            app_secret_key="x",
            database_url="x",
            metabase_planning_youtrack_enabled=True,
        )
    assert Settings._secure_origin(None) is False


def test_settings_allowed_hosts_rejects_missing_hostname(monkeypatch: pytest.MonkeyPatch) -> None:
    """Cover the defensive hostname check independently of Pydantic URL validation."""
    configured = Settings(_env_file=None, app_secret_key="x", database_url="x")
    monkeypatch.setattr(configured, "app_base_url", "http://")
    with pytest.raises(RuntimeError, match="no hostname"):
        _ = configured.allowed_hosts
