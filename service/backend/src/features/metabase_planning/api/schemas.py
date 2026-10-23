"""Validate Metabase planning HTTP request bodies."""

from pydantic import BaseModel, Field, field_validator

from features.chat.api.schemas import AttachmentPath
from features.chat.domain.model_modes import ModelMode


class PlanningRunBody(BaseModel):
    """Represent the first user description of one requested Metabase Question."""

    content: str = Field(min_length=1, max_length=100_000)
    attachments: list[AttachmentPath] = Field(default_factory=list, max_length=20)
    model_mode: ModelMode | None = None

    @field_validator("content")
    @classmethod
    def normalize_content(cls, value: str) -> str:
        """Strip and reject an empty planning message."""
        normalized = value.strip()
        if not normalized:
            raise ValueError("Message cannot be empty")
        return normalized


class PlanningCorrectionBody(PlanningRunBody):
    """Represent a correction guarded by the current workflow version."""

    workflow_version: int = Field(ge=0)


class MatchDecisionBody(BaseModel):
    """Guard candidate acceptance or rejection against stale browser state."""

    workflow_version: int = Field(ge=0)


class ReviewBody(BaseModel):
    """Represent an idempotent confirmed review submission."""

    workflow_version: int = Field(ge=0)
    plan_revision: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
