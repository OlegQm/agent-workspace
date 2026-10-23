"""Test persisted Metabase planning records."""

from sqlalchemy import inspect

from features.metabase_planning.infrastructure.persistence.models import (
    MetabasePlanningOperation,
    MetabasePlanningState,
)
from infrastructure.database.models import Conversation


def test_conversation_has_server_authoritative_kind_and_planning_state() -> None:
    """Store planning type separately from user-visible titles."""
    columns = inspect(Conversation).columns
    state_foreign_key = next(iter(MetabasePlanningState.__table__.c.conversation_id.foreign_keys))

    assert columns.kind.default.arg == "standard"
    assert columns.kind.server_default.arg.text == "'standard'"
    assert state_foreign_key.target_fullname == "conversations.id"
    assert state_foreign_key.ondelete == "CASCADE"


def test_planning_state_persists_revisions_candidate_plan_and_review_link() -> None:
    """Keep every action-driving value in one conversation-owned record."""
    columns = inspect(MetabasePlanningState).columns

    assert set(columns.keys()) >= {
        "conversation_id",
        "workflow_state",
        "requirements_revision",
        "workflow_version",
        "discovery_status",
        "discovery_signature",
        "candidate_question_id",
        "candidate_collection_id",
        "accepted_question_id",
        "plan_revision",
        "structured_plan",
        "youtrack_issue_id",
        "last_submitted_plan_revision",
        "issue_status",
        "issue_status_checked_at",
    }


def test_planning_operation_has_per_conversation_idempotency_constraint() -> None:
    """Prevent concurrent tabs from creating duplicate review operations."""
    constraints = inspect(MetabasePlanningOperation).local_table.constraints

    assert any(
        constraint.name == "uq_metabase_planning_operation_idempotency"
        for constraint in constraints
    )
    assert MetabasePlanningOperation.__table__.c.conversation_id.foreign_keys.pop().ondelete == (
        "CASCADE"
    )
