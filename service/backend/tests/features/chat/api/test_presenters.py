"""Test chat persistence presenters."""

import uuid

import pytest

from features.chat.api.presenters import (
    resolve_event_cursor,
    serialize_conversation,
    serialize_conversation_detail,
    serialize_message,
    serialize_run,
)
from features.metabase_planning.infrastructure.persistence.models import MetabasePlanningState
from infrastructure.database.models import AgentRun, Conversation, Message, User, utcnow


@pytest.mark.unit
def test_chat_record_serializers_preserve_public_fields() -> None:
    """Serialize conversation, message, and run records through stable response fields."""
    now = utcnow()
    conversation_id = uuid.uuid4()
    conversation = Conversation(
        id=conversation_id,
        user_id=uuid.uuid4(),
        agent_id="assistant",
        title="Question",
        created_at=now,
        updated_at=now,
    )
    message = Message(
        id=uuid.uuid4(),
        conversation_id=conversation_id,
        role="assistant",
        content="Answer",
        attachments=["report.xlsx"],
        created_at=now,
    )
    run = AgentRun(
        id=uuid.uuid4(),
        conversation_id=conversation_id,
        user_id=uuid.uuid4(),
        agent_id="assistant",
        status="completed",
        model_mode="medium",
        error=None,
        created_at=now,
        updated_at=now,
    )

    assert serialize_conversation(conversation)["id"] == str(conversation_id)
    assert serialize_message(message)["attachments"] == ["report.xlsx"]
    assert serialize_run(run)["model_mode"] == "medium"


@pytest.mark.integration
async def test_conversation_detail_orders_messages_and_runs(database) -> None:
    """Load persisted detail records in their established display order."""
    async with database() as session:
        user = User(username="presenter", password_hash="unused", agent_id="assistant")
        session.add(user)
        await session.flush()
        conversation = Conversation(user_id=user.id, agent_id="assistant", title="Question")
        session.add(conversation)
        await session.flush()
        session.add(Message(conversation_id=conversation.id, role="user", content="Question"))
        session.add(
            AgentRun(
                conversation_id=conversation.id,
                user_id=user.id,
                agent_id="assistant",
                status="completed",
            )
        )
        await session.commit()
        detail = await serialize_conversation_detail(conversation, session)

    assert [message["content"] for message in detail["messages"]] == ["Question"]
    assert [run["status"] for run in detail["runs"]] == ["completed"]


@pytest.mark.integration
async def test_conversation_detail_includes_authoritative_planning_snapshot(database) -> None:
    """Load planning state by conversation kind without parsing chat text."""
    async with database() as session:
        user = User(username="planner-presenter", password_hash="unused", agent_id="assistant")
        session.add(user)
        await session.flush()
        conversation = Conversation(
            user_id=user.id,
            agent_id="assistant",
            title="Question",
            kind="metabase_planning",
        )
        session.add(conversation)
        await session.flush()
        session.add(MetabasePlanningState(conversation_id=conversation.id))
        await session.commit()
        detail = await serialize_conversation_detail(conversation, session)

    assert detail["planning"]["state"] == "collecting"


@pytest.mark.unit
@pytest.mark.parametrize(
    ("after", "last_event_id", "expected"),
    [(3, "8", 3), (None, " 8 ", 8), (None, None, 0), (None, " ", 0)],
)
def test_event_cursor_precedence(after, last_event_id, expected: int) -> None:
    """Resolve explicit and EventSource cursors using fixed precedence."""
    assert resolve_event_cursor(after, last_event_id) == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    ("after", "last_event_id", "message"),
    [(None, "invalid", "Invalid Last-Event-ID"), (-1, None, "cannot be negative")],
)
def test_event_cursor_rejects_invalid_values(after, last_event_id, message: str) -> None:
    """Reject malformed and negative event cursors."""
    with pytest.raises(ValueError, match=message):
        resolve_event_cursor(after, last_event_id)
