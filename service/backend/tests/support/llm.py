"""Provide an explicit test LLM profile without production credentials."""

from features.agents.infrastructure.configuration.llm import LLMProfile


def configured_llm_profile() -> LLMProfile:
    """Return the established Codex model mapping for test agents."""
    return LLMProfile.model_validate({
        "provider": "openai-codex",
        "api_mode": "codex_responses",
        "auth_method": "oauth",
        "openai_runtime": "auto",
        "models": {
            "small": {"id": "gpt-5.6-luna", "label": "Luna", "description": "GPT-5.6 Luna"},
            "medium": {"id": "gpt-5.6-terra", "label": "Terra", "description": "GPT-5.6 Terra"},
            "high": {"id": "gpt-5.6-sol", "label": "Sol", "description": "GPT-5.6 Sol"},
        },
        "compression": {"codex_responses_native": True},
    })
