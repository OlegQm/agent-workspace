"""Test identity persistence repositories."""

import uuid

import pytest
from fastapi import HTTPException

from features.chat.infrastructure.repositories import owned_conversation
from infrastructure.database.models import Conversation, User


@pytest.mark.integration
async def test_conversation_ownership_boundary(database) -> None:
    """Return only conversations owned by the supplied user and agent."""
    async with database() as session:
        user = User(username="owner", password_hash="unused", agent_id="assistant")
        session.add(user)
        await session.commit()
        await session.refresh(user)
        conversation = Conversation(user_id=user.id, agent_id="assistant", title="Owned")
        session.add(conversation)
        await session.commit()
        await session.refresh(conversation)

        assert await owned_conversation(conversation.id, user, session) is conversation
        with pytest.raises(HTTPException):
            await owned_conversation(uuid.uuid4(), user, session)
