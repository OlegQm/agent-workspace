"""Expose authenticated Metabase planning conversation operations."""

import uuid

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from features.agents.infrastructure.configuration.registry import get_agent
from features.chat.api.presenters import serialize_conversation, serialize_run
from features.chat.infrastructure.hermes.runtime import ensure_hermes_session_capability
from features.identity.api.dependencies import agent_user, get_db
from features.metabase_planning.api.presenters import planning_snapshot
from features.metabase_planning.api.schemas import (
    MatchDecisionBody,
    PlanningCorrectionBody,
    PlanningRunBody,
    ReviewBody,
)
from features.metabase_planning.application.matches import (
    accept_match,
    accepted_question_id,
    reject_match,
)
from features.metabase_planning.application.reviews import (
    ReviewCommand,
    ReviewSubmissionRejected,
    ReviewSubmissionUnavailable,
    submit_for_review,
)
from features.metabase_planning.application.status import (
    linked_issue_key,
    refresh_issue_status,
)
from features.metabase_planning.application.turns import (
    PlanningTurnCommand,
    queue_correction,
    queue_initial_turn,
)
from features.metabase_planning.domain.exceptions import (
    InvalidPlanningAttachment,
    PlanningConflict,
    PlanningConversationNotFound,
    StalePlanningState,
)
from features.metabase_planning.infrastructure.hermes.executor import execute_planning_run
from features.metabase_planning.infrastructure.youtrack.client import YouTrackReviewClient
from infrastructure.database.models import User
from infrastructure.settings import settings

router = APIRouter()


def _translate_error(exc: Exception) -> HTTPException:
    """Translate application errors into bounded public HTTP responses."""
    if isinstance(exc, PlanningConversationNotFound):
        return HTTPException(status_code=404, detail="Planning conversation not found")
    if isinstance(exc, (StalePlanningState, PlanningConflict)):
        return HTTPException(status_code=409, detail=str(exc) or "Planning state changed")
    if isinstance(exc, InvalidPlanningAttachment):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, PermissionError):
        return HTTPException(status_code=403, detail="Planning action is not available")
    if isinstance(exc, ReviewSubmissionRejected):
        return HTTPException(status_code=503, detail="Review service rejected the request")
    if isinstance(exc, ReviewSubmissionUnavailable):
        return HTTPException(status_code=503, detail="Review service is temporarily unavailable")
    return HTTPException(status_code=500, detail="Planning operation failed")


async def _ensure_runtime(agent_id: str) -> None:
    """Require the standard persistent Hermes session endpoints."""
    try:
        await ensure_hermes_session_capability(agent_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def review_gateway(client: httpx.AsyncClient) -> YouTrackReviewClient:
    """Build the YouTrack adapter only from complete server-side configuration."""
    if not settings.youtrack_review_configured or settings.youtrack_token is None:
        raise RuntimeError("YouTrack review is not configured")
    return YouTrackReviewClient(
        client,
        base_url=str(settings.youtrack_base_url),
        token=settings.youtrack_token.get_secret_value(),
        project_id=str(settings.youtrack_project_id),
        assignee_id=str(settings.youtrack_assignee_id),
        assignee_field_id=str(settings.youtrack_assignee_field_id),
    )


@router.post("/api/metabase-planning/conversations/runs", status_code=202)
async def start_planning_conversation(
    body: PlanningRunBody,
    background_tasks: BackgroundTasks,
    user: User = Depends(agent_user),
    session: AsyncSession = Depends(get_db),
):
    """Create one persisted planning conversation and queue its first turn."""
    await _ensure_runtime(user.agent_id)
    agent = get_agent(user.agent_id)
    try:
        conversation, run = await queue_initial_turn(
            PlanningTurnCommand(
                content=body.content,
                attachments=body.attachments,
                model_mode=body.model_mode.value if body.model_mode else agent.llm.default_mode,
            ),
            user,
            agent,
            session,
        )
    except Exception as exc:
        raise _translate_error(exc) from exc
    background_tasks.add_task(execute_planning_run, run.id)
    return {
        "conversation": {
            **serialize_conversation(conversation),
            "planning": await planning_snapshot(session, conversation.id),
        },
        "run": serialize_run(run),
    }


@router.post("/api/metabase-planning/conversations/{conversation_id}/runs", status_code=202)
async def continue_planning_conversation(
    conversation_id: uuid.UUID,
    body: PlanningCorrectionBody,
    background_tasks: BackgroundTasks,
    user: User = Depends(agent_user),
    session: AsyncSession = Depends(get_db),
):
    """Invalidate stale actions and queue one user correction."""
    await _ensure_runtime(user.agent_id)
    agent = get_agent(user.agent_id)
    try:
        run = await queue_correction(
            conversation_id,
            PlanningTurnCommand(
                content=body.content,
                attachments=body.attachments,
                model_mode=body.model_mode.value if body.model_mode else agent.llm.default_mode,
                workflow_version=body.workflow_version,
            ),
            user,
            agent,
            session,
        )
    except Exception as exc:
        raise _translate_error(exc) from exc
    background_tasks.add_task(execute_planning_run, run.id)
    return {
        "run": serialize_run(run),
        "planning": await planning_snapshot(session, conversation_id),
    }


@router.post("/api/metabase-planning/conversations/{conversation_id}/match/accept")
async def accept_existing_question(
    conversation_id: uuid.UUID,
    body: MatchDecisionBody,
    user: User = Depends(agent_user),
    session: AsyncSession = Depends(get_db),
):
    """Resolve planning with the current server-authorized exact match."""
    try:
        await accept_match(
            session,
            conversation_id,
            user,
            get_agent(user.agent_id),
            expected_version=body.workflow_version,
        )
    except Exception as exc:
        raise _translate_error(exc) from exc
    return await planning_snapshot(session, conversation_id)


@router.post("/api/metabase-planning/conversations/{conversation_id}/match/reject")
async def reject_existing_question(
    conversation_id: uuid.UUID,
    body: MatchDecisionBody,
    user: User = Depends(agent_user),
    session: AsyncSession = Depends(get_db),
):
    """Reject the current exact match and resume requirements collection."""
    try:
        await reject_match(
            session,
            conversation_id,
            user,
            get_agent(user.agent_id),
            expected_version=body.workflow_version,
        )
    except Exception as exc:
        raise _translate_error(exc) from exc
    return await planning_snapshot(session, conversation_id)


@router.get("/api/metabase-planning/conversations/{conversation_id}/open")
async def open_existing_question(
    conversation_id: uuid.UUID,
    user: User = Depends(agent_user),
    session: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    """Redirect an authorized resolved chat to its accepted Metabase Question."""
    if not settings.metabase_links_configured or settings.metabase_public_url is None:
        raise HTTPException(status_code=503, detail="Metabase links are not configured")
    try:
        question_id = await accepted_question_id(
            session,
            conversation_id,
            user,
            get_agent(user.agent_id),
        )
    except Exception as exc:
        raise _translate_error(exc) from exc
    origin = settings.metabase_public_url.rstrip("/")
    return RedirectResponse(f"{origin}/question/{question_id}", status_code=307)


@router.post("/api/metabase-planning/conversations/{conversation_id}/review")
async def send_for_review(
    conversation_id: uuid.UUID,
    body: ReviewBody,
    user: User = Depends(agent_user),
    session: AsyncSession = Depends(get_db),
):
    """Create or update the single linked YouTrack issue after confirmation."""
    if not settings.youtrack_review_configured:
        raise HTTPException(status_code=503, detail="Review service is not configured")
    try:
        async with httpx.AsyncClient(
            timeout=20,
            trust_env=False,
            follow_redirects=False,
        ) as client:
            await submit_for_review(
                session,
                conversation_id,
                user,
                get_agent(user.agent_id),
                ReviewCommand(
                    workflow_version=body.workflow_version,
                    plan_revision=body.plan_revision,
                    idempotency_key=body.idempotency_key,
                ),
                review_gateway(client),
            )
    except Exception as exc:
        raise _translate_error(exc) from exc
    return await planning_snapshot(session, conversation_id)


@router.post("/api/metabase-planning/conversations/{conversation_id}/review/status")
async def refresh_review_status(
    conversation_id: uuid.UUID,
    user: User = Depends(agent_user),
    session: AsyncSession = Depends(get_db),
):
    """Perform one explicit read-only status refresh without background polling."""
    if not settings.youtrack_review_configured:
        raise HTTPException(status_code=503, detail="Review service is not configured")
    try:
        async with httpx.AsyncClient(
            timeout=10,
            trust_env=False,
            follow_redirects=False,
        ) as client:
            await refresh_issue_status(
                session,
                conversation_id,
                user,
                get_agent(user.agent_id),
                review_gateway(client),
            )
    except Exception as exc:
        raise _translate_error(exc) from exc
    return await planning_snapshot(session, conversation_id)


@router.get("/api/metabase-planning/conversations/{conversation_id}/review/open")
async def open_review_issue(
    conversation_id: uuid.UUID,
    user: User = Depends(agent_user),
    session: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    """Redirect an authorized owner to the linked review issue."""
    if not settings.youtrack_review_configured or settings.youtrack_base_url is None:
        raise HTTPException(status_code=503, detail="Review service is not configured")
    try:
        issue_key = await linked_issue_key(
            session,
            conversation_id,
            user,
            get_agent(user.agent_id),
        )
    except Exception as exc:
        raise _translate_error(exc) from exc
    origin = settings.youtrack_base_url.rstrip("/")
    return RedirectResponse(f"{origin}/issue/{issue_key}", status_code=307)
