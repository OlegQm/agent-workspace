"""Refresh informational YouTrack status only on explicit product triggers."""

import uuid
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from features.metabase_planning.domain.exceptions import PlanningConversationNotFound
from features.metabase_planning.infrastructure.persistence.models import (
    MetabasePlanningOperation,
    MetabasePlanningState,
)
from infrastructure.database.models import Conversation, User, utcnow


class StatusGateway(Protocol):
    """Define the single read-only external status operation."""

    async def fetch_status(self, issue_id: str) -> str | None:
        """Fetch one current issue status."""


class StatusAgent(Protocol):
    """Expose the agent identity used for ownership checks."""

    id: str


async def refresh_issue_status(
    session: AsyncSession,
    conversation_id: uuid.UUID,
    user: User,
    agent: StatusAgent,
    gateway: StatusGateway,
) -> MetabasePlanningState:
    """Refresh status once while retaining the prior value on failure."""
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
    if state.youtrack_issue_id is None:
        raise ValueError("Planning conversation has no linked review issue")
    operation = MetabasePlanningOperation(
        conversation_id=conversation_id,
        operation_type="status_refresh",
        idempotency_key=f"status-{uuid.uuid4().hex}",
        requirements_revision=state.requirements_revision,
        plan_revision=state.plan_revision or None,
        status="pending",
        attempt_count=1,
    )
    session.add(operation)
    await session.flush()
    try:
        refreshed = await gateway.fetch_status(state.youtrack_issue_id)
    except Exception:
        operation.status = "failed"
        operation.safe_error_code = "status_unavailable"
        state.issue_status_refresh_error = "status_unavailable"
    else:
        operation.status = "completed"
        state.issue_status = refreshed
        state.issue_status_checked_at = utcnow()
        state.issue_status_refresh_error = None
    now = utcnow()
    operation.finished_at = now
    operation.updated_at = now
    state.updated_at = now
    await session.commit()
    return state


async def linked_issue_key(
    session: AsyncSession,
    conversation_id: uuid.UUID,
    user: User,
    agent: StatusAgent,
) -> str:
    """Return the safe readable key for an owned linked review issue."""
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
    if not state.youtrack_issue_key:
        raise ValueError("Planning conversation has no linked review issue")
    return state.youtrack_issue_key
