"""Test validated agent configuration models."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from features.agents.infrastructure.configuration import models


def agent_values(**overrides: object) -> dict[str, object]:
    """Return a minimal valid agent configuration mapping."""
    values: dict[str, object] = {
        "id": "assistant",
        "display_name": "Assistant",
        "username": "assistant",
        "sandbox_name": "open-agent-workspace-assistant",
        "hermes_url": "http://127.0.0.1:1455",
        "hermes_api_key_env": "ASSISTANT_HERMES_API_KEY",
        "host_port": 1455,
        "tool_gateway_port": 1456,
        "tool_gateway_token_env": "ASSISTANT_TOOL_GATEWAY_TOKEN",
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
    return values


@pytest.mark.unit
def test_agent_properties_read_runtime_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Preserve secret, workspace, and instruction property behavior."""
    config_dir = tmp_path / "agents"
    data_dir = tmp_path / "data"
    soul = config_dir / "prompts" / "assistant" / "SOUL.md"
    soul.parent.mkdir(parents=True)
    soul.write_text("Assistant instructions\n")
    soul.with_name("METABASE_PLANNER.md").write_text("Planner instructions\n")
    monkeypatch.setattr(models.settings, "agent_config_dir", config_dir)
    monkeypatch.setattr(models.settings, "agent_data_dir", data_dir)
    monkeypatch.setenv("ASSISTANT_HERMES_API_KEY", "secret")
    configured = models.AgentConfig.model_validate(agent_values())

    assert configured.hermes_api_key == "secret"
    assert configured.workspace_root == data_dir / "assistant" / "workspace"
    assert configured.instructions == "Assistant instructions"
    assert configured.metabase_planner_instructions == "Planner instructions"


@pytest.mark.unit
def test_agent_properties_fail_closed_without_secret_or_instructions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reject absent runtime credentials and empty instruction files."""
    config_dir = tmp_path / "agents"
    monkeypatch.setattr(models.settings, "agent_config_dir", config_dir)
    monkeypatch.delenv("ASSISTANT_HERMES_API_KEY", raising=False)
    configured = models.AgentConfig.model_validate(agent_values())
    with pytest.raises(RuntimeError, match="not configured"):
        _ = configured.hermes_api_key
    with pytest.raises(RuntimeError, match="instructions are unavailable"):
        _ = configured.instructions

    soul = config_dir / "prompts" / "assistant" / "SOUL.md"
    soul.parent.mkdir(parents=True)
    soul.write_text("   ")
    with pytest.raises(RuntimeError, match="instructions are empty"):
        _ = configured.instructions

    with pytest.raises(RuntimeError, match="planner instructions are unavailable"):
        _ = configured.metabase_planner_instructions

    planner = soul.with_name("METABASE_PLANNER.md")
    planner.write_text("   ")
    with pytest.raises(RuntimeError, match="planner instructions are empty"):
        _ = configured.metabase_planner_instructions


@pytest.mark.unit
def test_repository_planner_prompt_starts_with_an_instruction() -> None:
    """Keep the bundled planner prompt free of patch artifacts before its instruction text."""
    agent_id = "assistant"
    prompt = (Path.cwd() / "config" / "agents" / "prompts" / agent_id / "METABASE_PLANNER.md").read_text(
        encoding="utf-8"
    )

    assert prompt.startswith("You are the Metabase Question requirements planner")
    assert '"business_question": {' in prompt
    assert '"metrics": [' in prompt
    assert '"provenance": "user_confirmed"' in prompt


def test_agent_resources_preserve_server_authorized_metabase_scope() -> None:
    """Keep exact-match candidates inside collections and databases from the manifest."""
    resources = models.AgentResources(
        metabase_scope="assistant",
        metabase_collection_ids=[53, 64],
        metabase_database_ids=[3],
    )

    assert resources.metabase_collection_ids == [53, 64]
    assert resources.metabase_database_ids == [3]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"id": "A"}, "invalid agent id"),
        ({"workspace_subdir": "nested/path"}, "workspace_subdir"),
        ({"hermes_url": "https://example.test:1455"}, "loopback"),
        ({"hermes_url": "http://127.0.0.1:9999"}, "host_port"),
    ],
)
def test_agent_model_rejects_invalid_values(overrides: dict[str, object], message: str) -> None:
    """Preserve fail-closed model validation rules."""
    with pytest.raises(ValidationError, match=message):
        models.AgentConfig.model_validate(agent_values(**overrides))


@pytest.mark.unit
def test_agent_model_accepts_single_custom_workspace_directory() -> None:
    """Preserve support for a safe single-component workspace directory."""
    configured = models.AgentConfig.model_validate(agent_values(workspace_subdir="documents"))
    assert configured.workspace_subdir == "documents"


@pytest.mark.unit
def test_agent_llm_profile_selects_models_from_manifest() -> None:
    """Use the agent manifest as the source of Hermes provider and mode IDs."""
    profile = {
        "provider": "example-provider",
        "api_mode": "chat_completions",
        "auth_method": "api_key",
        "credential_env": "EXAMPLE_API_KEY",
        "default_mode": "high",
        "models": {
            "small": {"id": "example-small", "label": "Example Small"},
            "medium": {"id": "example-medium", "label": "Example Medium"},
            "high": {"id": "example-high", "label": "Example High"},
        },
    }
    configured = models.AgentConfig.model_validate(agent_values(llm=profile))

    assert configured.llm.provider == "example-provider"
    assert configured.llm.model_for_mode("high") == "example-high"
    assert configured.llm.default_mode == "high"
    assert configured.llm.public_modes()["small"] == "Example Small"


@pytest.mark.unit
def test_agent_llm_profile_rejects_missing_mode() -> None:
    """Do not silently route an unsupported UI mode to a fallback model."""
    profile = {
        "provider": "example-provider",
        "api_mode": "chat_completions",
        "auth_method": "api_key",
        "credential_env": "EXAMPLE_API_KEY",
        "models": {"medium": {"id": "example-medium", "label": "Example Medium"}},
    }

    with pytest.raises(ValidationError, match="small|high|models"):
        models.AgentConfig.model_validate(agent_values(llm=profile))
