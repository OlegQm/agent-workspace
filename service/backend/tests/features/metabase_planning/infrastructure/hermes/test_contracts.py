"""Test the machine-readable Hermes planner result contract."""

import pytest
from pydantic import ValidationError

from features.metabase_planning.infrastructure.hermes.contracts import (
    PlannerResult,
    parse_planner_result,
)


def _result(**overrides: object) -> dict[str, object]:
    """Build a minimal valid planner result."""
    value: dict[str, object] = {
        "assistant_message": "Which reporting period should this cover?",
        "signature": {
            "business_intent": "Track paid revenue",
            "metric_definition": "Paid revenue",
            "source": "Stripe",
            "population_filter": None,
            "period_comparison": None,
            "granularity": None,
            "visualization": None,
        },
        "discovery": {"status": "no_match", "candidate": None},
        "plan": None,
    }
    value.update(overrides)
    return value


def test_planner_result_accepts_a_non_matching_discovery_result() -> None:
    """Keep assistant wording separate from action-driving structured state."""
    result = PlannerResult.model_validate(_result())

    assert result.discovery.status == "no_match"
    assert result.plan is None
    assert not hasattr(result, "requirements_revision")


def test_exact_match_requires_complete_alignment_and_no_ambiguities() -> None:
    """Reject optimistic candidates that have not been fully verified."""
    candidate = {
        "question_id": 42,
        "collection_id": 53,
        "title": "Paid revenue",
        "summary": "Monthly paid revenue",
        "metabase_verified": True,
        "metric_aligned": True,
        "filters_aligned": True,
        "time_aligned": True,
        "grain_aligned": True,
        "visualization_aligned": False,
        "intent_aligned": True,
        "ambiguities": [],
    }

    with pytest.raises(ValidationError, match="fully aligned"):
        PlannerResult.model_validate(
            _result(discovery={"status": "exact_match", "candidate": candidate})
        )


def test_non_match_cannot_smuggle_a_candidate() -> None:
    """Expose a candidate action only for the exact-match state."""
    candidate = {
        "question_id": 42,
        "collection_id": 53,
        "title": "Paid revenue",
        "summary": "Monthly paid revenue",
        "metabase_verified": True,
        "metric_aligned": True,
        "filters_aligned": True,
        "time_aligned": True,
        "grain_aligned": True,
        "visualization_aligned": True,
        "intent_aligned": True,
        "ambiguities": [],
    }

    with pytest.raises(ValidationError, match="only valid"):
        PlannerResult.model_validate(
            _result(discovery={"status": "inconclusive", "candidate": candidate})
        )


def test_parser_accepts_only_one_json_object() -> None:
    """Reject prose-wrapped output so the client never parses assistant wording."""
    import json

    parsed = parse_planner_result(json.dumps(_result()))
    assert parsed.assistant_message.startswith("Which")

    with pytest.raises(ValueError, match="JSON object"):
        parse_planner_result(f"Result: {json.dumps(_result())}")
    with pytest.raises(TypeError, match="JSON object"):
        parse_planner_result(json.dumps([_result()]))
