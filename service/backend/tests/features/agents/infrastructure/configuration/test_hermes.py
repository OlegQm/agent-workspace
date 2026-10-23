"""Test generation of Hermes settings from one validated agent LLM profile."""

import pytest

from features.agents.infrastructure.configuration.hermes import render_hermes_config
from features.agents.infrastructure.configuration.llm import LLMProfile


@pytest.mark.unit
def test_render_codex_profile_preserves_existing_runtime_settings() -> None:
    """Keep the existing Codex API and native compaction configuration."""
    profile = LLMProfile.model_validate({
        "provider": "openai-codex",
        "api_mode": "codex_responses",
        "openai_runtime": "auto",
        "auth_method": "oauth",
        "models": {
            "small": {"id": "luna", "label": "Luna"},
            "medium": {"id": "terra", "label": "Terra"},
            "high": {"id": "sol", "label": "Sol"},
        },
        "compression": {
            "enabled": True,
            "codex_responses_native": True,
            "codex_responses_compact_threshold": 200_000,
            "in_place": True,
        },
    })

    generated = render_hermes_config({"agent": {"disabled_toolsets": ["memory"]}}, profile)

    assert generated["model"] == {
        "default": "terra",
        "provider": "openai-codex",
        "api_mode": "codex_responses",
        "openai_runtime": "auto",
    }
    assert generated["compression"] == profile.compression.model_dump()
    assert generated["agent"] == {"disabled_toolsets": ["memory"]}


@pytest.mark.unit
def test_render_non_codex_profile_omits_codex_only_settings() -> None:
    """Allow a compatible non-Codex profile without leaking Codex settings."""
    profile = LLMProfile.model_validate({
        "provider": "example-provider",
        "api_mode": "chat_completions",
        "auth_method": "api_key",
        "credential_env": "EXAMPLE_API_KEY",
        "default_mode": "high",
        "models": {
            "small": {"id": "small", "label": "Small"},
            "medium": {"id": "medium", "label": "Medium"},
            "high": {"id": "large", "label": "Large"},
        },
    })

    generated = render_hermes_config({}, profile)

    assert generated["model"] == {
        "default": "large", "provider": "example-provider", "api_mode": "chat_completions"
    }
    assert generated["compression"] == {"enabled": True, "in_place": True}
    assert "EXAMPLE_API_KEY" not in str(generated)
