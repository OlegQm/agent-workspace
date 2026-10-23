"""Test Hermes model identifier mapping."""

import pytest

from features.agents.infrastructure.configuration.llm import LLMProfile
from features.chat.domain.model_modes import ModelMode
from features.chat.infrastructure.hermes.models import model_id_for_mode


@pytest.fixture
def profile() -> LLMProfile:
    """Use non-Codex identifiers to detect any fixed runtime mapping."""
    return LLMProfile.model_validate({
        "provider": "example-provider",
        "api_mode": "chat_completions",
        "auth_method": "api_key",
        "credential_env": "EXAMPLE_API_KEY",
        "models": {
            "small": {"id": "example-small", "label": "Small"},
            "medium": {"id": "example-medium", "label": "Medium"},
            "high": {"id": "example-high", "label": "High"},
        },
    })


@pytest.mark.parametrize(
    ("mode", "model_id"),
    [
        (ModelMode.small, "example-small"),
        (ModelMode.medium, "example-medium"),
        (ModelMode.high, "example-high"),
    ],
)
def test_model_modes_map_to_agent_profile(
    profile: LLMProfile, mode: ModelMode, model_id: str
) -> None:
    """Map user-facing modes through the selected agent's profile."""
    assert model_id_for_mode(profile, mode) == model_id


def test_unknown_model_mode_is_rejected(profile: LLMProfile) -> None:
    """Reject arbitrary model identifiers outside the fixed mode contract."""
    with pytest.raises(ValueError):
        model_id_for_mode(profile, "arbitrary-model")
