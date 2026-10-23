"""Validate the structured result returned by the Hermes planning mode."""

import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from features.metabase_planning.domain.models import StructuredPlan
from features.metabase_planning.domain.signatures import DiscoverySignature


class ExistingQuestionCandidate(BaseModel):
    """Describe a Metabase Question verified against every requested dimension."""

    model_config = ConfigDict(frozen=True)

    question_id: int = Field(gt=0)
    collection_id: int = Field(gt=0)
    title: str = Field(min_length=1, max_length=500)
    summary: str = Field(min_length=1, max_length=2_000)
    metabase_verified: bool
    metric_aligned: bool
    filters_aligned: bool
    time_aligned: bool
    grain_aligned: bool
    visualization_aligned: bool
    intent_aligned: bool
    ambiguities: list[str] = Field(default_factory=list, max_length=20)

    @property
    def is_full_match(self) -> bool:
        """Return whether every conservative exact-match criterion is satisfied."""
        checks = (
            self.metabase_verified,
            self.metric_aligned,
            self.filters_aligned,
            self.time_aligned,
            self.grain_aligned,
            self.visualization_aligned,
            self.intent_aligned,
        )
        return all(checks) and not self.ambiguities


class DiscoveryResult(BaseModel):
    """Represent safe read-only discovery performed for one requirements revision."""

    model_config = ConfigDict(frozen=True)

    status: Literal["exact_match", "no_match", "inconclusive", "unavailable", "not_required"]
    candidate: ExistingQuestionCandidate | None = None

    @model_validator(mode="after")
    def validate_candidate(self) -> "DiscoveryResult":
        """Require a fully aligned candidate exclusively for an exact match."""
        if self.status == "exact_match":
            if self.candidate is None or not self.candidate.is_full_match:
                raise ValueError("exact match candidate must be fully aligned")
        elif self.candidate is not None:
            raise ValueError("candidate is only valid for an exact match")
        return self


class PlannerResult(BaseModel):
    """Separate user-facing prose from server-authoritative planning decisions."""

    model_config = ConfigDict(frozen=True)

    assistant_message: str = Field(min_length=1, max_length=100_000)
    signature: DiscoverySignature
    discovery: DiscoveryResult
    plan: StructuredPlan | None


def parse_planner_result(value: str) -> PlannerResult:
    """Parse a bare JSON object and reject prose or Markdown wrappers."""
    try:
        payload = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError("Planner output must be one JSON object") from exc
    if not isinstance(payload, dict):
        raise TypeError("Planner output must be one JSON object")
    return PlannerResult.model_validate(payload)
