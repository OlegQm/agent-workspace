"""Handle conversation and run HTTP operations for regular users."""

import uuid

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from features.agents.infrastructure.configuration.registry import get_agent
from features.chat.api.presenters import (
    resolve_event_cursor,
    serialize_conversation,
    serialize_conversation_detail,
    serialize_run,
)
from features.chat.api.schemas import ApprovalBody, RunBody
from features.chat.infrastructure.hermes.runtime import (
    approve_hermes_run,
    delete_hermes_session,
    ensure_hermes_session_capability,
    event_stream,
    execute_run,
    stop_hermes_run,
)
from features.chat.infrastructure.repositories import owned_conversation
from features.identity.api.dependencies import agent_user, get_db
from features.workspace.infrastructure.filesystem.service import safe_path
from infrastructure.database.models import (
    ACTIVE_RUN_STATUSES,
    AgentRun,
    Conversation,
    ConversationRuntime,
    Message,
    RunStatus,
    User,
    utcnow,
)

router = APIRouter()


@router.get("/api/conversations")
async def conversations(user: User = Depends(agent_user), session: AsyncSession = Depends(get_db)):
    """Handle conversations."""
    conversations = await session.scalars(
        select(Conversation)
        .where(Conversation.user_id == user.id, Conversation.agent_id == user.agent_id)
        .order_by(Conversation.updated_at.desc())
    )
    return [serialize_conversation(conversation) for conversation in conversations]


@router.get("/api/conversations/{conversation_id}")
async def conversation_detail(
    conversation_id: uuid.UUID,
    user: User = Depends(agent_user),
    session: AsyncSession = Depends(get_db),
):
    """Handle conversation detail."""
    conversation = await owned_conversation(conversation_id, user, session)
    return await serialize_conversation_detail(conversation, session)


@router.delete("/api/conversations/{conversation_id}", status_code=204)
async def delete_conversation(
    conversation_id: uuid.UUID,
    user: User = Depends(agent_user),
    session: AsyncSession = Depends(get_db),
):
    """Delete conversation."""
    conversation = await owned_conversation(conversation_id, user, session)
    runtime = await session.get(ConversationRuntime, conversation.id)
    hermes_session_id = runtime.hermes_session_id if runtime else None
    active = await session.scalar(
        select(AgentRun.id).where(
            AgentRun.conversation_id == conversation.id,
            AgentRun.status.in_(ACTIVE_RUN_STATUSES),
        )
    )
    if active:
        raise HTTPException(status_code=409, detail="Stop the active run first")
    await session.execute(delete(Conversation).where(Conversation.id == conversation.id))
    await session.commit()
    if hermes_session_id:
        await delete_hermes_session(user.agent_id, hermes_session_id)


async def queue_run(
    conversation: Conversation,
    body: RunBody,
    background_tasks: BackgroundTasks,
    user: User,
    session: AsyncSession,
) -> AgentRun:
    """Handle queue run."""
    runtime = await session.get(ConversationRuntime, conversation.id)
    if runtime is None or not runtime.hermes_session_id:
        raise HTTPException(
            status_code=409,
            detail="Conversation runtime state is unavailable",
        )
    try:
        await ensure_hermes_session_capability(user.agent_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    agent = get_agent(user.agent_id)
    attachments = []
    for relative in body.attachments:
        path = safe_path(agent.workspace_root, relative, must_exist=True)
        if not path.is_file():
            raise HTTPException(status_code=400, detail=f"Attachment is not a file: {relative}")
        attachments.append(relative)
    content = body.content.strip()
    if attachments:
        paths = "\n".join(f"- {agent.workspace_root / path}" for path in attachments)
        content += f"\n\nFiles available in your workspace:\n{paths}"
    message = Message(
        conversation_id=conversation.id,
        role="user",
        content=content,
        attachments=attachments,
    )
    run = AgentRun(
        conversation_id=conversation.id,
        user_id=user.id,
        agent_id=user.agent_id,
        model_mode=body.model_mode.value if body.model_mode else agent.llm.default_mode,
        status=RunStatus.queued.value,
    )
    session.add_all([message, run])
    conversation.updated_at = utcnow()
    if conversation.title == "New conversation":
        conversation.title = body.content.strip()[:80]
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=409, detail="Agent already has an active run")
    await session.refresh(run)
    background_tasks.add_task(execute_run, run.id)
    return run


@router.post("/api/conversations/runs", status_code=202)
async def start_new_conversation_run(
    body: RunBody,
    background_tasks: BackgroundTasks,
    user: User = Depends(agent_user),
    session: AsyncSession = Depends(get_db),
):
    """Start new conversation run."""
    conversation = Conversation(
        user_id=user.id,
        agent_id=user.agent_id,
        title=body.content.strip()[:80],
    )
    session.add(conversation)
    await session.flush()
    session.add(
        ConversationRuntime(
            conversation_id=conversation.id,
            hermes_session_id=f"open-agent-workspace_{uuid.uuid4().hex}",
        )
    )
    await session.flush()
    run = await queue_run(conversation, body, background_tasks, user, session)
    return {
        "conversation": serialize_conversation(conversation),
        "run": serialize_run(run),
    }


@router.post("/api/conversations/{conversation_id}/runs", status_code=202)
async def start_run(
    conversation_id: uuid.UUID,
    body: RunBody,
    background_tasks: BackgroundTasks,
    user: User = Depends(agent_user),
    session: AsyncSession = Depends(get_db),
):
    """Start run."""
    conversation = await owned_conversation(conversation_id, user, session)
    if conversation.kind != "standard":
        raise HTTPException(status_code=409, detail="Use the planning conversation endpoint")
    run = await queue_run(conversation, body, background_tasks, user, session)
    return serialize_run(run)


async def owned_run(run_id: uuid.UUID, user: User, session: AsyncSession) -> AgentRun:
    """Handle owned run."""
    run = await session.scalar(
        select(AgentRun).where(
            AgentRun.id == run_id,
            AgentRun.user_id == user.id,
            AgentRun.agent_id == user.agent_id,
        )
    )
    if run is None:
        raise HTTPException(status_code=404)
    return run


@router.get("/api/runs/{run_id}")
async def run_detail(
    run_id: uuid.UUID,
    user: User = Depends(agent_user),
    session: AsyncSession = Depends(get_db),
):
    """Run detail."""
    return serialize_run(await owned_run(run_id, user, session))


@router.get("/api/runs/{run_id}/events")
async def run_events(
    run_id: uuid.UUID,
    request: Request,
    after: int | None = None,
    user: User = Depends(agent_user),
    session: AsyncSession = Depends(get_db),
):
    """Run events."""
    await owned_run(run_id, user, session)
    try:
        cursor = resolve_event_cursor(after, request.headers.get("last-event-id"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return StreamingResponse(event_stream(run_id, cursor), media_type="text/event-stream")


@router.post("/api/runs/{run_id}/stop", status_code=202)
async def stop_run(
    run_id: uuid.UUID,
    user: User = Depends(agent_user),
    session: AsyncSession = Depends(get_db),
):
    """Stop run."""
    run = await owned_run(run_id, user, session)
    if run.status not in ACTIVE_RUN_STATUSES:
        return serialize_run(run)
    await stop_hermes_run(run)
    return {"status": "stopping"}


@router.post("/api/runs/{run_id}/approval", status_code=202)
async def approve_run(
    run_id: uuid.UUID,
    body: ApprovalBody,
    user: User = Depends(agent_user),
    session: AsyncSession = Depends(get_db),
):
    """Handle approve run."""
    if body.decision not in {"once", "session", "always", "deny"}:
        raise HTTPException(status_code=400, detail="Invalid approval decision")
    run = await owned_run(run_id, user, session)
    if run.status != RunStatus.waiting_approval.value:
        raise HTTPException(status_code=409, detail="Run is not waiting for approval")
    try:
        await approve_hermes_run(run, body.decision)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="Agent runtime is unavailable") from exc
    return {"status": "running"}
