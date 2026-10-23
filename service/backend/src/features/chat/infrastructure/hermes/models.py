"""Map domain reasoning modes to Hermes runtime model identifiers."""

from features.agents.infrastructure.configuration.llm import LLMProfile
from features.chat.domain.model_modes import ModelMode


def model_id_for_mode(profile: LLMProfile, value: str | ModelMode) -> str:
    """Return one configured Hermes model identifier for a reasoning mode."""
    return profile.model_for_mode(ModelMode(value).value)
