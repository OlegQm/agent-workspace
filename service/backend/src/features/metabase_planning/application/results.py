"""Apply validated Hermes planner results to persisted workflow state."""

import uuid
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from features.metabase_planning.infrastructure.hermes.contracts import PlannerResult
from features.metabase_planning.infrastructure.persistence.models import MetabasePlanningState
from infrastructure.database.models import Conversation, Message, utcnow


class MetabaseScope(Protocol):
    """Describe the server-authorized Metabase resources needed here."""

    metabase_collection_ids: list[int]


class PlanningAgentScope(Protocol):
    """Expose the resource scope of one configured agent."""

    resources: MetabaseScope


async def apply_planner_result(
    session: AsyncSession,
    conversation_id: uuid.UUID,
    result: PlannerResult,
    agent: PlanningAgentScope,
    *,
    expected_requirements_revision: int,
) -> None:
    """Persist one current structured result and its user-facing message atomically."""
    state = await session.scalar(
        select(MetabasePlanningState)
        .where(MetabasePlanningState.conversation_id == conversation_id)
        .with_for_update()
    )
    if state is None:
        raise RuntimeError("Planning state is unavailable")
    if expected_requirements_revision != state.requirements_revision:
        raise ValueError("Planning result targeted a stale requirements revision")

    candidate = result.discovery.candidate
    if candidate is not None and candidate.collection_id not in set(
        agent.resources.metabase_collection_ids
    ):
        raise ValueError("Candidate is outside the authorized Metabase scope")

    state.discovery_status = result.discovery.status
    state.discovery_for_revision = expected_requirements_revision
    state.discovery_signature = {
        "business_intent": result.signature.business_intent,
        "metric_definition": result.signature.metric_definition,
        "source": result.signature.source,
        "population_filter": result.signature.population_filter,
        "period_comparison": result.signature.period_comparison,
        "granularity": result.signature.granularity,
        "visualization": result.signature.visualization,
    }
    if candidate is not None:
        state.workflow_state = "match_proposed"
        state.candidate_question_id = candidate.question_id
        state.candidate_collection_id = candidate.collection_id
        state.candidate_title = candidate.title
        state.candidate_summary = candidate.summary
        state.candidate_for_revision = expected_requirements_revision
    elif result.plan is not None:
        result.plan.validate_for_submission()
        state.workflow_state = "plan_ready"
        state.plan_revision += 1
        state.plan_for_requirements_revision = expected_requirements_revision
        state.structured_plan = result.plan.model_dump(mode="json")
    else:
        state.workflow_state = "collecting"
    state.workflow_version += 1
    state.updated_at = utcnow()
    conversation = await session.get(Conversation, conversation_id)
    if conversation is not None:
        conversation.updated_at = utcnow()
    session.add(
        Message(
            conversation_id=conversation_id,
            role="assistant",
            content=result.assistant_message,
        )
    )
    await session.commit()
