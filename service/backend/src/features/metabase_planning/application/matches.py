"""Accept or reject a current existing Metabase Question candidate."""

import uuid
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from features.metabase_planning.domain.exceptions import (
    PlanningConversationNotFound,
    StalePlanningState,
)
from features.metabase_planning.infrastructure.persistence.models import MetabasePlanningState
from infrastructure.database.models import Conversation, User, utcnow


class MatchAgentResources(Protocol):
    """Expose the configured Metabase collections used for authorization."""

    metabase_collection_ids: list[int]


class MatchAgent(Protocol):
    """Describe one agent and its Metabase authorization scope."""

    id: str
    resources: MatchAgentResources


async def _current_candidate(
    session: AsyncSession,
    conversation_id: uuid.UUID,
    user: User,
    agent: MatchAgent,
    expected_version: int,
) -> MetabasePlanningState:
    """Lock and validate one user-owned current match candidate."""
    state = await session.scalar(
        select(MetabasePlanningState)
        .join(Conversation)
        .where(
            Conversation.id == conversation_id,
            Conversation.user_id == user.id,
            Conversation.agent_id == agent.id,
            Conversation.kind == "metabase_planning",
        )
        .with_for_update()
    )
    if state is None:
        raise PlanningConversationNotFound
    if state.workflow_version != expected_version:
        raise StalePlanningState("Workflow state changed; reload the conversation")
    if (
        state.workflow_state != "match_proposed"
        or state.candidate_question_id is None
        or state.candidate_collection_id not in set(agent.resources.metabase_collection_ids)
        or state.candidate_for_revision != state.requirements_revision
    ):
        raise PermissionError("Candidate is no longer available in the authorized Metabase scope")
    return state


async def accept_match(
    session: AsyncSession,
    conversation_id: uuid.UUID,
    user: User,
    agent: MatchAgent,
    *,
    expected_version: int,
) -> MetabasePlanningState:
    """Resolve planning with the current server-stored existing Question."""
    state = await _current_candidate(session, conversation_id, user, agent, expected_version)
    state.accepted_question_id = state.candidate_question_id
    state.accepted_at = utcnow()
    state.workflow_state = "resolved_existing"
    state.workflow_version += 1
    state.updated_at = utcnow()
    await session.commit()
    return state


async def reject_match(
    session: AsyncSession,
    conversation_id: uuid.UUID,
    user: User,
    agent: MatchAgent,
    *,
    expected_version: int,
) -> MetabasePlanningState:
    """Reject a candidate and resume normal requirements collection."""
    state = await _current_candidate(session, conversation_id, user, agent, expected_version)
    state.workflow_state = "collecting"
    state.candidate_question_id = None
    state.candidate_collection_id = None
    state.candidate_title = None
    state.candidate_summary = None
    state.candidate_for_revision = None
    state.workflow_version += 1
    state.updated_at = utcnow()
    await session.commit()
    return state


async def accepted_question_id(
    session: AsyncSession,
    conversation_id: uuid.UUID,
    user: User,
    agent: MatchAgent,
) -> int:
    """Return an accepted Question only while its collection remains authorized."""
    state = await session.scalar(
        select(MetabasePlanningState)
        .join(Conversation)
        .where(
            Conversation.id == conversation_id,
            Conversation.user_id == user.id,
            Conversation.agent_id == agent.id,
            Conversation.kind == "metabase_planning",
        )
    )
    if state is None:
        raise PlanningConversationNotFound
    if (
        state.workflow_state != "resolved_existing"
        or state.accepted_question_id is None
        or state.candidate_collection_id not in set(agent.resources.metabase_collection_ids)
    ):
        raise PermissionError("Accepted Question is unavailable in the authorized Metabase scope")
    return state.accepted_question_id
