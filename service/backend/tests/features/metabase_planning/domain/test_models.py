"""Test structured Metabase planning domain models."""

import pytest

from features.metabase_planning.domain.models import (
    PlanStatement,
    Provenance,
    StructuredPlan,
)


def plan_with(provenance: Provenance) -> StructuredPlan:
    """Build the smallest complete plan with configurable evidence provenance."""
    statement = PlanStatement(text="Monthly paid revenue", provenance=provenance)
    return StructuredPlan(
        business_question=statement,
        metrics=[statement],
        sources=[PlanStatement(text="Stripe", provenance=Provenance.authorized_discovery)],
        period=[PlanStatement(text="Previous calendar month", provenance=Provenance.user_confirmed)],
        grain=[PlanStatement(text="One point per day", provenance=Provenance.user_confirmed)],
        dimensions=[],
        filters=[],
        comparisons=[],
        exclusions=[],
        visualization=[PlanStatement(text="Line chart", provenance=Provenance.user_confirmed)],
        expected_interpretation=[],
        assumptions=[],
        explicit_answers=[],
    )


def test_submission_plan_accepts_user_and_authorized_source_evidence() -> None:
    """Allow authoritative requirements confirmed by the user or a scoped source."""
    plan = plan_with(Provenance.user_confirmed)

    plan.validate_for_submission()


def test_submission_plan_rejects_file_context_as_authoritative_evidence() -> None:
    """Reject workspace-file context until the user confirms it as a requirement."""
    plan = plan_with(Provenance.file_context)

    with pytest.raises(ValueError, match="file context"):
        plan.validate_for_submission()


def test_plan_requires_nonempty_business_question() -> None:
    """Reject an empty business question in a machine-readable planner result."""
    with pytest.raises(ValueError):
        PlanStatement(text="  ", provenance=Provenance.user_confirmed)
