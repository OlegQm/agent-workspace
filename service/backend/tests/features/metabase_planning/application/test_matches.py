"""Test deterministic existing-Question decisions."""

import uuid
from types import SimpleNamespace

import pytest

from features.metabase_planning.application.matches import (
    accept_match,
    accepted_question_id,
    reject_match,
)
from features.metabase_planning.domain.exceptions import (
    PlanningConversationNotFound,
    StalePlanningState,
)
from features.metabase_planning.infrastructure.persistence.models import MetabasePlanningState
from infrastructure.database.models import Conversation, User


async def _candidate(database, user: User, *, collection_id: int = 53):
    """Persist one current candidate for the supplied user."""
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
                workflow_state="match_proposed",
                workflow_version=4,
                candidate_question_id=42,
                candidate_collection_id=collection_id,
                candidate_title="Revenue",
                candidate_summary="Exact match",
                candidate_for_revision=0,
            )
        )
        await session.commit()
        return conversation.id


@pytest.mark.integration
async def test_accept_and_reject_require_current_server_scope_and_version(database, users) -> None:
    """Allow only the current owner to decide a current in-scope candidate."""
    agent = SimpleNamespace(id="assistant", resources=SimpleNamespace(metabase_collection_ids=[53]))
    accepted_id = await _candidate(database, users[0])
    rejected_id = await _candidate(database, users[0])

    async with database() as session:
        accepted = await accept_match(session, accepted_id, users[0], agent, expected_version=4)
        rejected = await reject_match(session, rejected_id, users[0], agent, expected_version=4)
    async with database() as session:
        accepted_id_value = await accepted_question_id(session, accepted_id, users[0], agent)

    assert accepted.workflow_state == "resolved_existing"
    assert accepted.accepted_question_id == 42
    assert accepted.workflow_version == 5
    assert accepted_id_value == 42
    assert rejected.workflow_state == "collecting"
    assert rejected.candidate_question_id is None


@pytest.mark.integration
async def test_match_decision_rejects_stale_and_out_of_scope_candidates(database, users) -> None:
    """Fail closed when browser state or manifest authorization no longer matches."""
    conversation_id = await _candidate(database, users[0], collection_id=999)
    agent = SimpleNamespace(id="assistant", resources=SimpleNamespace(metabase_collection_ids=[53]))

    async with database() as session:
        with pytest.raises(StalePlanningState):
            await accept_match(session, conversation_id, users[0], agent, expected_version=3)
    async with database() as session:
        with pytest.raises(PermissionError, match="scope"):
            await accept_match(session, conversation_id, users[0], agent, expected_version=4)


@pytest.mark.integration
async def test_match_lookup_rejects_missing_owner_and_unavailable_acceptance(database, users) -> None:
    """Hide absent chats and accepted Questions removed from the configured scope."""
    agent = SimpleNamespace(id="assistant", resources=SimpleNamespace(metabase_collection_ids=[53]))
    conversation_id = await _candidate(database, users[0], collection_id=999)
    async with database() as session:
        with pytest.raises(PlanningConversationNotFound):
            await accept_match(session, conversation_id, users[1], agent, expected_version=4)
        state = await session.get(MetabasePlanningState, conversation_id)
        state.workflow_state = "resolved_existing"
        state.accepted_question_id = 42
        await session.commit()
    async with database() as session:
        with pytest.raises(PermissionError, match="unavailable"):
            await accepted_question_id(session, conversation_id, users[0], agent)
        with pytest.raises(PlanningConversationNotFound):
            await accepted_question_id(session, uuid.uuid4(), users[0], agent)
