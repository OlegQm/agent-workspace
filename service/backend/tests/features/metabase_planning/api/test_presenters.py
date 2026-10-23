"""Test authoritative Metabase planning API presentation."""

import uuid

import pytest

from features.metabase_planning.api.presenters import planning_snapshot, serialize_planning_state
from features.metabase_planning.infrastructure.persistence.models import (
    MetabasePlanningOperation,
    MetabasePlanningState,
)
from infrastructure.database.models import utcnow


def state(**values) -> MetabasePlanningState:
    """Build a persisted planning state with stable defaults."""
    defaults = {
        "conversation_id": uuid.uuid4(),
        "workflow_state": "collecting",
        "requirements_revision": 2,
        "workflow_version": 5,
        "plan_revision": 0,
    }
    defaults.update(values)
    return MetabasePlanningState(**defaults)


def test_ready_plan_exposes_create_then_update_from_persisted_fields() -> None:
    """Drive review button mode from current revisions and linked issue identity."""
    record = state(
        workflow_state="plan_ready",
        plan_revision=3,
        plan_for_requirements_revision=2,
        structured_plan={"business_question": {"text": "Revenue"}},
    )

    created = serialize_planning_state(record)
    assert created["actions"]["send_for_review"] == {
        "visible": True,
        "enabled": True,
        "mode": "create",
        "disabled_reason": None,
    }

    record.youtrack_issue_id = "2-4"
    record.youtrack_issue_key = "BI-4"
    assert serialize_planning_state(record)["actions"]["send_for_review"]["mode"] == "update"


def test_pending_operation_disables_actions_and_admin_never_receives_actions() -> None:
    """Disable concurrent commands and remove actions from read-only admin detail."""
    record = state(
        workflow_state="match_proposed",
        candidate_question_id=42,
        candidate_title="Revenue",
        candidate_summary="Matches the request",
        candidate_for_revision=2,
    )
    operation = MetabasePlanningOperation(
        conversation_id=record.conversation_id,
        operation_type="discovering",
        idempotency_key="discovery-2",
        requirements_revision=2,
        status="pending",
    )

    regular = serialize_planning_state(record, operation)
    assert regular["actions"]["accept_match"]["visible"] is True
    assert regular["actions"]["accept_match"]["enabled"] is False
    assert regular["operation"]["status"] == "pending"

    admin = serialize_planning_state(record, operation, administrator=True)
    assert all(not action["visible"] for action in admin["actions"].values())


def test_resolved_and_submitted_metadata_are_serialized_without_raw_urls() -> None:
    """Expose safe identifiers while leaving external URLs server-owned."""
    now = utcnow()
    record = state(
        workflow_state="resolved_existing",
        accepted_question_id=42,
        accepted_at=now,
        youtrack_issue_id="2-8",
        youtrack_issue_key="BI-8",
        issue_status="Open",
        issue_status_checked_at=now,
        last_submitted_plan_revision=1,
        last_submitted_at=now,
    )

    payload = serialize_planning_state(record)

    assert payload["actions"]["open_metabase"]["enabled"] is True
    assert payload["review"] == {
        "issue_key": "BI-8",
        "status": "Open",
        "last_submitted_revision": 1,
        "submitted_at": now,
        "status_checked_at": now,
        "status_refresh_error": None,
    }
    assert "url" not in payload["review"]


@pytest.mark.integration
async def test_snapshot_returns_none_without_state_and_selects_latest_operation(
    database, users
) -> None:
    """Initialize missing chats safely and expose only the latest durable operation."""
    conversation_id = uuid.uuid4()
    async with database() as session:
        assert await planning_snapshot(session, conversation_id) is None

    record = state(conversation_id=conversation_id)
    first = MetabasePlanningOperation(
        conversation_id=conversation_id,
        operation_type="status_refresh",
        idempotency_key="first",
        requirements_revision=2,
        status="failed",
    )
    second = MetabasePlanningOperation(
        conversation_id=conversation_id,
        operation_type="review_create",
        idempotency_key="second",
        requirements_revision=2,
        status="pending",
    )
    from infrastructure.database.models import Conversation

    async with database() as session:
        conversation = Conversation(
            id=conversation_id,
            user_id=users[0].id,
            agent_id="assistant",
            kind="metabase_planning",
        )
        session.add(conversation)
        await session.flush()
        session.add_all([record, first, second])
        await session.commit()
        payload = await planning_snapshot(session, conversation_id)

    assert payload is not None
    assert payload["operation"]["id"] == str(second.id)
