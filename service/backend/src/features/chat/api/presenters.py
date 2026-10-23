"""Present chat persistence records through stable HTTP response contracts."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.database.models import AgentRun, Conversation, Message


def serialize_conversation(conversation: Conversation) -> dict:
    """Serialize conversation."""
    return {
        "id": str(conversation.id),
        "title": conversation.title,
        "kind": conversation.kind,
        "created_at": conversation.created_at,
        "updated_at": conversation.updated_at,
    }


def serialize_message(message: Message) -> dict:
    """Serialize message."""
    return {
        "id": str(message.id),
        "role": message.role,
        "content": message.content,
        "attachments": message.attachments,
        "created_at": message.created_at,
    }


def serialize_run(run: AgentRun) -> dict:
    """Serialize run."""
    return {
        "id": str(run.id),
        "conversation_id": str(run.conversation_id),
        "status": run.status,
        "model_mode": run.model_mode,
        "error": run.error,
        "created_at": run.created_at,
        "updated_at": run.updated_at,
    }


async def serialize_conversation_detail(
    conversation: Conversation,
    session: AsyncSession,
    *,
    administrator: bool = False,
) -> dict:
    """Serialize a conversation together with its persisted messages and runs."""
    messages = await session.scalars(
        select(Message)
        .where(Message.conversation_id == conversation.id)
        .order_by(Message.created_at, Message.id)
    )
    runs = await session.scalars(
        select(AgentRun)
        .where(AgentRun.conversation_id == conversation.id)
        .order_by(AgentRun.created_at.desc())
    )
    result = {
        **serialize_conversation(conversation),
        "messages": [serialize_message(message) for message in messages],
        "runs": [serialize_run(run) for run in runs],
    }
    if conversation.kind == "metabase_planning":
        from features.metabase_planning.api.presenters import planning_snapshot

        result["planning"] = await planning_snapshot(
            session, conversation.id, administrator=administrator
        )
    return result


def resolve_event_cursor(after: int | None, last_event_id: str | None) -> int:
    """Resolve event cursor."""
    if after is not None:
        cursor = after
    elif last_event_id and last_event_id.strip():
        try:
            cursor = int(last_event_id.strip())
        except ValueError as exc:
            raise ValueError("Invalid Last-Event-ID") from exc
    else:
        cursor = 0
    if cursor < 0:
        raise ValueError("Event cursor cannot be negative")
    return cursor
