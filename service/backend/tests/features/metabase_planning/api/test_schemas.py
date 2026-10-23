"""Test Metabase planning request validation."""

import pytest
from pydantic import ValidationError

from features.metabase_planning.api.schemas import (
    MatchDecisionBody,
    PlanningRunBody,
    ReviewBody,
)


def test_planning_run_and_revision_commands_are_bounded() -> None:
    """Validate planning messages and optimistic concurrency values."""
    body = PlanningRunBody(content="Need monthly revenue", attachments=["example.xlsx"])
    assert body.content == "Need monthly revenue"
    assert body.model_mode is None
    assert MatchDecisionBody(workflow_version=3).workflow_version == 3
    assert ReviewBody(workflow_version=3, plan_revision=2, idempotency_key="retry-1")

    with pytest.raises(ValidationError):
        PlanningRunBody(content=" ")
    with pytest.raises(ValidationError):
        ReviewBody(workflow_version=-1, plan_revision=1, idempotency_key="x")
