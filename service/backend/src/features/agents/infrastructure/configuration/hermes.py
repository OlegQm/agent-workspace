"""Render provider-specific Hermes settings from a validated agent profile."""

from copy import deepcopy
from typing import Any

from features.agents.infrastructure.configuration.llm import LLMProfile


def render_hermes_config(template: dict[str, Any], profile: LLMProfile) -> dict[str, Any]:
    """Preserve tool setup while replacing model and compression settings."""
    config = deepcopy(template)
    model = {
        "default": profile.model_for_mode(profile.default_mode),
        "provider": profile.provider,
        "api_mode": profile.api_mode,
    }
    if profile.openai_runtime is not None:
        model["openai_runtime"] = profile.openai_runtime
    config["model"] = model
    compression = {
        "enabled": profile.compression.enabled,
        "in_place": profile.compression.in_place,
    }
    if profile.api_mode == "codex_responses":
        compression["codex_responses_native"] = profile.compression.codex_responses_native
        compression["codex_responses_compact_threshold"] = (
            profile.compression.codex_responses_compact_threshold
        )
    config["compression"] = compression
    return config
