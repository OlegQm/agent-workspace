"""Validate the provider profile shared by Hermes and the application."""

import re
from collections.abc import Mapping
from copy import deepcopy
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Mode = Literal["small", "medium", "high"]
ApiMode = Literal["codex_responses", "chat_completions", "responses", "anthropic_messages"]
ENV_NAME = re.compile(r"^[A-Z][A-Z0-9_]*$")
PROVIDER_NAME = re.compile(r"^[a-z][a-z0-9_-]*$")


class ModelDefinition(BaseModel):
    """Name one model available behind a user-facing reasoning mode."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    description: str | None = Field(default=None, min_length=1)


class CompressionConfig(BaseModel):
    """Describe Hermes session compression without assuming one API transport."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    codex_responses_native: bool = False
    codex_responses_compact_threshold: int = Field(default=200_000, gt=0)
    in_place: bool = True


class LLMProfile(BaseModel):
    """Keep one agent's provider, authentication, and model choices coherent."""

    model_config = ConfigDict(extra="forbid")

    provider: str
    api_mode: ApiMode
    auth_method: Literal["oauth", "api_key"]
    credential_env: str | None = None
    openai_runtime: str | None = None
    default_mode: Mode = "medium"
    models: dict[Mode, ModelDefinition]
    compression: CompressionConfig = Field(default_factory=CompressionConfig)

    @model_validator(mode="after")
    def validate_profile(self) -> "LLMProfile":
        """Reject incomplete modes and provider-specific setting mismatches."""
        if not PROVIDER_NAME.fullmatch(self.provider):
            raise ValueError("provider must be a Hermes provider identifier")
        if set(self.models) != {"small", "medium", "high"}:
            raise ValueError("models must define small, medium, and high")
        if self.auth_method == "api_key":
            if not self.credential_env or not ENV_NAME.fullmatch(self.credential_env):
                raise ValueError("api_key authentication requires credential_env")
        elif self.credential_env is not None:
            raise ValueError("OAuth profiles cannot include credential_env")
        if self.api_mode == "codex_responses" and self.provider != "openai-codex":
            raise ValueError("codex_responses requires openai-codex")
        if self.compression.codex_responses_native and self.api_mode != "codex_responses":
            raise ValueError("native Codex compression requires codex_responses")
        if self.openai_runtime is not None and self.provider != "openai-codex":
            raise ValueError("openai_runtime requires openai-codex")
        return self

    def model_for_mode(self, mode: str) -> str:
        """Resolve only a configured user-facing mode to a Hermes model ID."""
        try:
            return self.models[mode].id
        except KeyError as exc:
            raise ValueError(f"Unsupported model mode: {mode}") from exc

    def public_modes(self) -> dict[Mode, str]:
        """Expose display names without provider credentials or runtime settings."""
        return {mode: item.label for mode, item in self.models.items()}

    def public_mode_descriptors(self) -> list[dict[str, str]]:
        """Return ordered, non-secret names for the frontend mode selector."""
        return [
            {
                "value": mode,
                "label": self.models[mode].label,
                "description": self.models[mode].description or self.models[mode].id,
            }
            for mode in ("small", "medium", "high")
        ]


def profile_from_environment(
    values: Mapping[str, Any], agent_id: str, environment: Mapping[str, str]
) -> LLMProfile:
    """Apply global and agent-scoped non-secret overrides to one manifest profile."""
    profile = deepcopy(dict(values))

    def override(name: str) -> str | None:
        """Prefer a non-empty agent override over the global setting."""
        scoped = environment.get(f"LLM_{agent_id.upper()}_{name}")
        global_value = environment.get(f"LLM_{name}")
        return scoped if scoped not in {None, ""} else global_value or None

    for name, field in (
        ("PROVIDER", "provider"),
        ("API_MODE", "api_mode"),
        ("AUTH_METHOD", "auth_method"),
        ("CREDENTIAL_ENV", "credential_env"),
        ("DEFAULT_MODE", "default_mode"),
        ("OPENAI_RUNTIME", "openai_runtime"),
    ):
        value = override(name)
        if value is not None:
            profile[field] = value
    if profile.get("provider") != "openai-codex":
        profile.pop("openai_runtime", None)
    compression = profile.setdefault("compression", {})
    for name, field in (
        ("COMPRESSION_ENABLED", "enabled"),
        ("NATIVE_COMPACTION", "codex_responses_native"),
        ("COMPACT_THRESHOLD", "codex_responses_compact_threshold"),
        ("COMPRESSION_IN_PLACE", "in_place"),
    ):
        value = override(name)
        if value is not None:
            compression[field] = value
    for mode in ("small", "medium", "high"):
        model = override(f"MODEL_{mode.upper()}")
        label = override(f"LABEL_{mode.upper()}")
        description = override(f"DESCRIPTION_{mode.upper()}")
        if model is not None:
            profile["models"][mode]["id"] = model
            profile["models"][mode]["label"] = label or model
            profile["models"][mode]["description"] = description or model
        elif label is not None:
            profile["models"][mode]["label"] = label
        if model is None and description is not None:
            profile["models"][mode]["description"] = description
    return LLMProfile.model_validate(profile)
