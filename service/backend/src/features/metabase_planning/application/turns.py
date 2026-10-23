"""Create planning conversations and invalidate state on user corrections."""

import uuid
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from features.metabase_planning.domain.exceptions import (
    PlanningConflict,
    PlanningConversationNotFound,
    StalePlanningState,
)
from features.metabase_planning.infrastructure.attachments.access import (
    validate_attachment_paths,
)
from features.metabase_planning.infrastructure.persistence.models import MetabasePlanningState
from infrastructure.database.models import (
    AgentRun,
    Conversation,
    ConversationRuntime,
    Message,
    RunStatus,
    User,
    utcnow,
)


class PlanningAgent(Protocol):
    """Describe the agent values required to validate one planning turn."""

    id: str
    workspace_root: object


@dataclass(frozen=True)
class PlanningTurnCommand:
    """Carry a validated planning message into the application layer."""

    content: str
    attachments: list[str]
    model_mode: str
    workflow_version: int | None = None


async def _commit_run(session: AsyncSession, run: AgentRun) -> AgentRun:
    """Commit a queued run while translating the active-agent uniqueness boundary."""
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise PlanningConflict("Agent already has an active run") from exc
    await session.refresh(run)
    return run


async def queue_initial_turn(
    command: PlanningTurnCommand,
    user: User,
    agent: PlanningAgent,
    session: AsyncSession,
) -> tuple[Conversation, AgentRun]:
    """Persist a new marked conversation and its first planning run."""
    attachments = validate_attachment_paths(agent.workspace_root, command.attachments)  # type: ignore[arg-type]
    conversation = Conversation(
        user_id=user.id,
        agent_id=agent.id,
        title=command.content[:80],
        kind="metabase_planning",
    )
    session.add(conversation)
    await session.flush()
    run = AgentRun(
        conversation_id=conversation.id,
        user_id=user.id,
        agent_id=agent.id,
        model_mode=command.model_mode,
        status=RunStatus.queued.value,
    )
    session.add_all(
        [
            ConversationRuntime(
                conversation_id=conversation.id,
                hermes_session_id=f"open-agent-workspace_plan_{uuid.uuid4().hex}",
            ),
            MetabasePlanningState(conversation_id=conversation.id),
            Message(
                conversation_id=conversation.id,
                role="user",
                content=command.content,
                attachments=attachments,
            ),
            run,
        ]
    )
    return conversation, await _commit_run(session, run)


async def queue_correction(
    conversation_id: uuid.UUID,
    command: PlanningTurnCommand,
    user: User,
    agent: PlanningAgent,
    session: AsyncSession,
) -> AgentRun:
    """Invalidate stale actions and persist a correction as one transaction."""
    row = await session.execute(
        select(Conversation, MetabasePlanningState)
        .join(MetabasePlanningState)
        .where(
            Conversation.id == conversation_id,
            Conversation.user_id == user.id,
            Conversation.agent_id == agent.id,
            Conversation.kind == "metabase_planning",
        )
        .with_for_update()
    )
    result = row.one_or_none()
    if result is None:
        raise PlanningConversationNotFound
    conversation, state = result
    if command.workflow_version != state.workflow_version:
        raise StalePlanningState("Workflow state changed; reload the conversation")
    attachments = validate_attachment_paths(agent.workspace_root, command.attachments)  # type: ignore[arg-type]
    state.requirements_revision += 1
    state.workflow_version += 1
    state.workflow_state = "collecting"
    state.discovery_status = "not_started"
    state.candidate_question_id = None
    state.candidate_collection_id = None
    state.candidate_title = None
    state.candidate_summary = None
    state.candidate_for_revision = None
    state.accepted_question_id = None
    state.accepted_at = None
    state.structured_plan = None
    state.plan_for_requirements_revision = None
    state.updated_at = utcnow()
    conversation.updated_at = utcnow()
    run = AgentRun(
        conversation_id=conversation.id,
        user_id=user.id,
        agent_id=agent.id,
        model_mode=command.model_mode,
        status=RunStatus.queued.value,
    )
    session.add_all(
        [
            Message(
                conversation_id=conversation.id,
                role="user",
                content=command.content,
                attachments=attachments,
            ),
            run,
        ]
    )
    return await _commit_run(session, run)
