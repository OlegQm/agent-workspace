"""Characterize the agent manifest registry."""

from pathlib import Path

import pytest
import yaml

from features.agents.infrastructure.configuration import registry as agents


@pytest.mark.unit
def test_bundled_setup_has_one_neutral_agent_profile() -> None:
    """Keep the included quick-start profile generic and closed to data by default."""
    repository = Path(__file__).resolve().parents[7]
    agent_dir = repository / "config" / "agents"
    profiles = sorted(path.name for path in agent_dir.glob("*.yaml"))

    assert profiles == ["assistant.yaml"]
    profile = yaml.safe_load((agent_dir / "assistant.yaml").read_text(encoding="utf-8"))
    assert profile["id"] == "assistant"
    assert profile["display_name"] == "Assistant"
    assert profile["resources"]["metabase_collection_ids"] == []
    assert profile["resources"]["metabase_database_ids"] == []
    assert profile["resources"]["bigquery_datasets"] == []
    assert profile["resources"]["google_ads_customer_ids"] == []
    assert profile["resources"]["google_analytics_property_ids"] == []
    assert profile["resources"]["superfaktura_companies"] == []
    prompts = agent_dir / "prompts" / "assistant"
    for prompt in prompts.glob("*.md"):
        text = prompt.read_text(encoding="utf-8").casefold()
        assert "finance" not in text
        assert "marketing" not in text


def write_manifest(directory: Path, name: str, **overrides: object) -> None:
    """Write a minimal valid agent manifest with optional contract variations."""
    values: dict[str, object] = {
        "id": name,
        "display_name": name.title(),
        "username": name,
        "sandbox_name": f"open-agent-workspace-{name}",
        "hermes_url": "http://127.0.0.1:1455",
        "hermes_api_key_env": f"{name.upper()}_HERMES_API_KEY",
        "host_port": 1455,
        "tool_gateway_port": 1456,
        "tool_gateway_token_env": f"{name.upper()}_TOOL_GATEWAY_TOKEN",
        "tools": ["metabase"],
        "resources": {},
        "llm": {
            "provider": "openai-codex",
            "api_mode": "codex_responses",
            "auth_method": "oauth",
            "models": {
                "small": {"id": "gpt-5.6-luna", "label": "Luna"},
                "medium": {"id": "gpt-5.6-terra", "label": "Terra"},
                "high": {"id": "gpt-5.6-sol", "label": "Sol"},
            },
        },
    }
    values.update(overrides)
    import yaml

    (directory / f"{name}.yaml").write_text(yaml.safe_dump(values), encoding="utf-8")


@pytest.mark.unit
def test_agent_manifest_loads_and_reads_runtime_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Preserve manifest validation, workspace resolution, and instruction loading."""
    config = tmp_path / "agents"
    config.mkdir()
    write_manifest(config, "assistant")
    monkeypatch.setattr(agents.settings, "agent_config_dir", config)
    agents.load_agents.cache_clear()

    loaded = agents.load_agents()

    assert list(loaded) == ["assistant"]
    assert agents.get_agent("assistant") is loaded["assistant"]
    with pytest.raises(LookupError, match="unknown agent"):
        agents.get_agent("missing")


@pytest.mark.unit
def test_agent_manifest_rejects_conflicting_local_ports(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reject one manifest that reuses its own runtime port."""
    config = tmp_path / "agents"
    config.mkdir()
    write_manifest(config, "assistant", tool_gateway_port=1455)
    monkeypatch.setattr(agents.settings, "agent_config_dir", config)
    agents.load_agents.cache_clear()

    with pytest.raises(RuntimeError, match="reuses"):
        agents.load_agents()


@pytest.mark.unit
def test_agent_manifest_rejects_duplicate_resources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reject two manifests that allocate the same sandbox or runtime port."""
    config = tmp_path / "agents"
    config.mkdir()
    write_manifest(config, "assistant")
    write_manifest(config, "helper", sandbox_name="open-agent-workspace-assistant")
    monkeypatch.setattr(agents.settings, "agent_config_dir", config)
    agents.load_agents.cache_clear()
    with pytest.raises(RuntimeError, match="duplicate sandbox"):
        agents.load_agents()


@pytest.mark.unit
def test_agent_manifest_remaining_fail_closed_branches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cover empty registries, duplicate IDs, shared ports, and mismatched runtime URLs."""
    config = tmp_path / "agents"
    config.mkdir()
    monkeypatch.setattr(agents.settings, "agent_config_dir", config)
    agents.load_agents.cache_clear()
    with pytest.raises(RuntimeError, match="no agent manifests"):
        agents.load_agents()

    write_manifest(config, "assistant")
    write_manifest(
        config,
        "helper",
        sandbox_name="open-agent-workspace-helper",
        host_port=1457,
        tool_gateway_port=1456,
        hermes_url="http://127.0.0.1:1457",
    )
    agents.load_agents.cache_clear()
    with pytest.raises(RuntimeError, match="reuses"):
        agents.load_agents()

    import yaml

    duplicate = yaml.safe_load((config / "assistant.yaml").read_text())
    duplicate["sandbox_name"] = "another"
    duplicate["host_port"] = 1555
    duplicate["tool_gateway_port"] = 1556
    duplicate["hermes_url"] = "http://127.0.0.1:1555"
    (config / "duplicate.yaml").write_text(yaml.safe_dump(duplicate))
    (config / "helper.yaml").unlink()
    agents.load_agents.cache_clear()
    with pytest.raises(RuntimeError, match="duplicate agent id"):
        agents.load_agents()
