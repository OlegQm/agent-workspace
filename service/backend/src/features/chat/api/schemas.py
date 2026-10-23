"""Define validated HTTP payloads owned by the chat API."""

from typing import Annotated

from pydantic import BaseModel, Field, field_validator

from features.chat.domain.model_modes import ModelMode

AttachmentPath = Annotated[str, Field(min_length=1, max_length=500)]


class RunBody(BaseModel):
    """Represent the validated Run request payload."""

    content: str = Field(min_length=1, max_length=100_000)
    attachments: list[AttachmentPath] = Field(default_factory=list, max_length=20)
    model_mode: ModelMode | None = None

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        """Validate content."""
        value = value.strip()
        if not value:
            raise ValueError("Message cannot be empty")
        return value


class ApprovalBody(BaseModel):
    """Represent the validated Approval request payload."""

    decision: str = Field(min_length=1, max_length=16)
