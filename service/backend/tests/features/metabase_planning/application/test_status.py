"""Test explicit informational YouTrack status refreshes."""

import uuid
from types import SimpleNamespace

import pytest

from features.metabase_planning.application.status import linked_issue_key, refresh_issue_status
from features.metabase_planning.domain.exceptions import PlanningConversationNotFound
from features.metabase_planning.infrastructure.persistence.models import MetabasePlanningState
from infrastructure.database.models import Conversation, User


async def _submitted(database, user: User):
    """Create a submitted planning conversation with a known status."""
    async with database() as session:
        conversation = Conversation(
            user_id=user.id,
            agent_id="assistant",
            title="Revenue",
            kind="metabase_planning",
        )
        session.add(conversation)
        await session.flush()
        session.add(
            MetabasePlanningState(
                conversation_id=conversation.id,
                workflow_state="submitted",
                youtrack_issue_id="2-7",
                youtrack_issue_key="BI-7",
                issue_status="Open",
            )
        )
        await session.commit()
        return conversation.id


@pytest.mark.integration
async def test_refresh_replaces_status_only_after_a_successful_read(database, users) -> None:
    """Update informational status and clear an earlier safe error."""
    conversation_id = await _submitted(database, users[0])

    class Gateway:
        """Return a deterministic status without network access."""

        async def fetch_status(self, issue_id: str) -> str:
            """Return the fake issue status."""
            assert issue_id == "2-7"
            return "Done"

    async with database() as session:
        state = await refresh_issue_status(
            session, conversation_id, users[0], SimpleNamespace(id="assistant"), Gateway()
        )

    assert state.issue_status == "Done"
    assert state.issue_status_refresh_error is None
    assert state.issue_status_checked_at is not None


@pytest.mark.integration
async def test_failed_refresh_preserves_last_known_status(database, users) -> None:
    """Keep useful known status when a read-only refresh is unavailable."""
    conversation_id = await _submitted(database, users[0])

    class Gateway:
        """Simulate an unavailable read-only integration."""

        async def fetch_status(self, issue_id: str) -> str:
            """Raise a bounded fake transport error."""
            raise RuntimeError("remote body must not escape")

    async with database() as session:
        state = await refresh_issue_status(
            session, conversation_id, users[0], SimpleNamespace(id="assistant"), Gateway()
        )

    assert state.issue_status == "Open"
    assert state.issue_status_refresh_error == "status_unavailable"


@pytest.mark.integration
async def test_status_operations_require_owned_linked_issue(database, users) -> None:
    """Reject absent, foreign, and not-yet-submitted planning conversations."""
    agent = SimpleNamespace(id="assistant")
    conversation_id = await _submitted(database, users[0])
    async with database() as session:
        assert await linked_issue_key(session, conversation_id, users[0], agent) == "BI-7"
        with pytest.raises(PlanningConversationNotFound):
            await linked_issue_key(session, conversation_id, users[1], agent)
        state = await session.get(MetabasePlanningState, conversation_id)
        state.youtrack_issue_id = None
        state.youtrack_issue_key = None
        await session.commit()
    async with database() as session:
        with pytest.raises(ValueError, match="no linked review issue"):
            await refresh_issue_status(session, conversation_id, users[0], agent, object())
        with pytest.raises(ValueError, match="no linked review issue"):
            await linked_issue_key(session, conversation_id, users[0], agent)
        with pytest.raises(PlanningConversationNotFound):
            await refresh_issue_status(session, uuid.uuid4(), users[0], agent, object())
