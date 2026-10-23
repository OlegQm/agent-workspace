"""Test agent-scoped LLM environment overrides and validation."""

import pytest
from pydantic import ValidationError

from features.agents.infrastructure.configuration.llm import LLMProfile, profile_from_environment


def codex_values() -> dict:
    """Provide a complete non-secret default profile."""
    return {
        "provider": "openai-codex",
        "api_mode": "codex_responses",
        "openai_runtime": "auto",
        "auth_method": "oauth",
        "models": {
            "small": {"id": "luna", "label": "Luna"},
            "medium": {"id": "terra", "label": "Terra"},
            "high": {"id": "sol", "label": "Sol"},
        },
        "compression": {"codex_responses_native": True},
    }


@pytest.mark.unit
def test_agent_environment_overrides_global_model_without_changing_other_agents() -> None:
    """Apply a scoped model override after a global value and update its label."""
    environment = {
        "LLM_MODEL_MEDIUM": "global-medium",
        "LLM_ASSISTANT_MODEL_MEDIUM": "assistant-medium",
    }

    assistant = profile_from_environment(codex_values(), "assistant", environment)
    other_agent = profile_from_environment(codex_values(), "other-agent", environment)

    assert assistant.model_for_mode("medium") == "assistant-medium"
    assert assistant.public_modes()["medium"] == "assistant-medium"
    assert assistant.public_mode_descriptors()[1]["description"] == "assistant-medium"
    assert other_agent.model_for_mode("medium") == "global-medium"


@pytest.mark.unit
def test_environment_can_select_an_api_key_provider_as_one_validated_profile() -> None:
    """Switch provider, transport, authentication, and compaction together."""
    environment = {
        "LLM_ASSISTANT_PROVIDER": "example-provider",
        "LLM_ASSISTANT_API_MODE": "chat_completions",
        "LLM_ASSISTANT_AUTH_METHOD": "api_key",
        "LLM_ASSISTANT_CREDENTIAL_ENV": "EXAMPLE_API_KEY",
        "LLM_ASSISTANT_NATIVE_COMPACTION": "false",
        "LLM_ASSISTANT_MODEL_SMALL": "example-small",
        "LLM_ASSISTANT_MODEL_MEDIUM": "example-medium",
        "LLM_ASSISTANT_MODEL_HIGH": "example-high",
        "LLM_ASSISTANT_DEFAULT_MODE": "high",
    }

    profile = profile_from_environment(codex_values(), "assistant", environment)

    assert profile.provider == "example-provider"
    assert profile.api_mode == "chat_completions"
    assert profile.credential_env == "EXAMPLE_API_KEY"
    assert profile.openai_runtime is None
    assert profile.compression.codex_responses_native is False
    assert profile.model_for_mode(profile.default_mode) == "example-high"


@pytest.mark.unit
def test_invalid_environment_override_fails_validation() -> None:
    """Never fall back silently after a misspelled mode or incompatible API mode."""
    with pytest.raises(ValidationError, match="codex_responses"):
        profile_from_environment(
            codex_values(), "assistant", {"LLM_ASSISTANT_PROVIDER": "example-provider"}
        )


@pytest.mark.unit
@pytest.mark.parametrize(
    ("change", "error"),
    [
        ({"provider": "not valid"}, "provider"),
        ({"auth_method": "api_key", "credential_env": None}, "credential_env"),
        ({"auth_method": "api_key", "credential_env": "bad-name"}, "credential_env"),
        ({"credential_env": "EXAMPLE_API_KEY"}, "OAuth"),
        ({"api_mode": "chat_completions"}, "native Codex"),
    ],
)
def test_profile_rejects_incompatible_configuration(change: dict, error: str) -> None:
    """Reject unsafe or impossible provider, transport, and auth combinations."""
    values = codex_values() | change
    with pytest.raises(ValidationError, match=error):
        profile_from_environment(values, "assistant", {})


@pytest.mark.unit
def test_profile_rejects_codex_runtime_on_other_provider() -> None:
    """Reject a raw manifest with an OpenAI-specific setting on another provider."""
    values = codex_values() | {
        "provider": "example-provider",
        "api_mode": "chat_completions",
        "compression": {"codex_responses_native": False},
    }
    with pytest.raises(ValidationError, match="openai_runtime"):
        LLMProfile.model_validate(values)


@pytest.mark.unit
def test_profile_exposes_only_known_modes_and_fallback_description() -> None:
    """Keep arbitrary model IDs out of the request contract."""
    profile = profile_from_environment(codex_values(), "assistant", {})
    assert profile.public_mode_descriptors()[0]["description"] == "luna"
    with pytest.raises(ValueError, match="Unsupported model mode"):
        profile.model_for_mode("unknown")


@pytest.mark.unit
def test_scoped_environment_supports_display_and_compression_overrides() -> None:
    """Apply explicit labels, descriptions, and bounded compression settings."""
    environment = {
        "LLM_ASSISTANT_LABEL_SMALL": "Fast",
        "LLM_ASSISTANT_DESCRIPTION_SMALL": "Fast model",
        "LLM_ASSISTANT_MODEL_MEDIUM": "balanced-model",
        "LLM_ASSISTANT_LABEL_MEDIUM": "Balanced",
        "LLM_ASSISTANT_DESCRIPTION_MEDIUM": "Balanced model",
        "LLM_ASSISTANT_OPENAI_RUNTIME": "auto",
        "LLM_ASSISTANT_COMPRESSION_ENABLED": "false",
        "LLM_ASSISTANT_COMPACT_THRESHOLD": "100000",
        "LLM_ASSISTANT_COMPRESSION_IN_PLACE": "false",
    }
    profile = profile_from_environment(codex_values(), "assistant", environment)

    assert profile.public_mode_descriptors()[0]["description"] == "Fast model"
    assert profile.public_mode_descriptors()[1] == {
        "value": "medium", "label": "Balanced", "description": "Balanced model"
    }
    assert profile.compression.enabled is False
    assert profile.compression.codex_responses_compact_threshold == 100_000
    assert profile.compression.in_place is False
