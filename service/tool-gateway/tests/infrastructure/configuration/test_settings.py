"""Characterize all Tool Gateway settings branches."""

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from tool_gateway.infrastructure.configuration.settings import Settings


def build_settings(tmp_path: Path, **overrides) -> Settings:
    """Build isolated settings without reading a developer environment file."""
    values = {
        "gateway_role": "assistant",
        "gateway_port": 18765,
        "gateway_token_env": "TEST_GATEWAY_TOKEN",
        "agent_config_dir": tmp_path / "config",
        "agent_data_dir": tmp_path / "agents",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[arg-type]


def write_manifest(path: Path) -> None:
    """Write a complete manifest used by settings property tests."""
    path.mkdir(parents=True)
    (path / "assistant.yaml").write_text(
        yaml.safe_dump(
            {
                "id": "assistant",
                "tools": ["metabase"],
                "resources": {
                    "environment": "prod",
                    "metabase_database_ids": [2, 1, 2],
                    "bigquery_datasets": ["project.beta", "project.alpha", "project.alpha"],
                    "google_ads_customer_ids": ["123-456", "", "123456"],
                    "meta_ad_account_ids": ["act_123", "", "456"],
                    "tool_export_limits": {
                        "metabase": {"max_rows": 7, "max_bytes": 99},
                        "rows_only": {"max_rows": 8},
                        "bytes_only": {"max_bytes": 100},
                    },
                },
            }
        )
    )


def test_settings_validators_and_token(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Characterize role, host, API-version, and token validation."""
    configured = build_settings(tmp_path)
    monkeypatch.delenv("TEST_GATEWAY_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="is required"):
        _ = configured.token
    monkeypatch.setenv("TEST_GATEWAY_TOKEN", "short")
    with pytest.raises(RuntimeError, match="at least 32"):
        _ = configured.token
    token = "x" * 32
    monkeypatch.setenv("TEST_GATEWAY_TOKEN", token)
    assert configured.token == token

    for field, value in (
        ("gateway_role", "../assistant"),
        ("gateway_host", "0.0.0.0"),
        ("meta_graph_api_version", "latest"),
    ):
        with pytest.raises(ValidationError):
            build_settings(tmp_path, **{field: value})
    assert build_settings(tmp_path, gateway_host="::1").gateway_host == "::1"
    assert build_settings(tmp_path, meta_graph_api_version="v24").meta_graph_api_version == "v24"


def test_manifest_resource_and_workspace_properties(tmp_path: Path) -> None:
    """Characterize manifest-backed normalized resource properties."""
    config = tmp_path / "config"
    write_manifest(config)
    configured = build_settings(tmp_path, agent_config_dir=config)

    assert configured.manifest.id == "assistant"
    assert configured.workspace == (tmp_path / "agents/assistant/workspace").resolve()
    assert configured.allowed_bigquery_datasets == ["project.alpha", "project.beta"]
    assert configured.allowed_metabase_database_ids == [1, 2]
    assert configured.allowed_google_ads_customer_ids == ["123456"]
    assert configured.allowed_meta_ad_account_ids == ["123", "456"]
    assert configured.export_max_rows("metabase") == 7
    assert configured.export_max_bytes("metabase") == 99
    assert configured.export_max_rows("bytes_only") == configured.tool_export_max_rows
    assert configured.export_max_bytes("rows_only") == configured.tool_export_max_bytes
    assert configured.export_max_rows("missing") == configured.tool_export_max_rows
    assert configured.export_max_bytes("missing") == configured.tool_export_max_bytes


def test_source_credentials_are_typed_and_optional(tmp_path: Path) -> None:
    """Characterize absent, valid, malformed, and missing credential profiles."""
    configured = build_settings(tmp_path)
    assert configured.source_credentials == {}

    missing = build_settings(tmp_path, source_credentials_file=tmp_path / "missing.yaml")
    assert missing.source_credentials == {}

    credentials = tmp_path / "credentials.yaml"
    credentials.write_text(
        yaml.safe_dump(
            {
                "metabase": {"default": {"api_key": "key"}, "broken": "value"},
                "invalid": {"default": "value"},
            }
        )
    )
    configured = build_settings(tmp_path, source_credentials_file=credentials)
    assert configured.credential("metabase", "default") == {"api_key": "key"}
    assert configured.optional_credential("metabase") == {"api_key": "key"}
    assert configured.optional_credential("missing") == {}
    with pytest.raises(RuntimeError, match="not configured"):
        configured.credential("missing", "default")
    with pytest.raises(TypeError, match="must be a mapping"):
        configured.credential("metabase", "broken")
    with pytest.raises(TypeError, match="must be a mapping"):
        configured.optional_credential("invalid")

    credentials.write_text("- not-a-mapping\n")
    with pytest.raises(TypeError, match="must contain a mapping"):
        _ = configured.source_credentials
    credentials.write_text("")
    assert configured.source_credentials == {}
