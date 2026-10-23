"""Test model modes behavior."""

from features.chat.domain.model_modes import ModelMode


def test_fixed_model_mode_contract() -> None:
    """Preserve the complete public mode-to-model contract."""
    assert [mode.value for mode in ModelMode] == ["small", "medium", "high"]
    assert ModelMode("medium") is ModelMode.medium
