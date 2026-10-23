"""Test validated HTTP payloads owned by the chat slice."""

import pytest
from pydantic import ValidationError

from features.chat.api.schemas import ApprovalBody, RunBody
from features.chat.domain.model_modes import ModelMode


def test_run_body_normalizes_content_and_rejects_blank_messages() -> None:
    """Verify that run payloads retain only meaningful user content."""
    assert RunBody(content="  Analyze revenue  ").content == "Analyze revenue"
    with pytest.raises(ValidationError, match="Message cannot be empty"):
        RunBody(content=" \n ")


def test_run_and_approval_payloads_use_fixed_validated_values() -> None:
    """Verify that chat payloads preserve the explicit model and approval data."""
    body = RunBody(content="Question", attachments=["report.xlsx"], model_mode=ModelMode.high)

    assert body.attachments == ["report.xlsx"]
    assert body.model_mode is ModelMode.high
    assert ApprovalBody(decision="once").decision == "once"
