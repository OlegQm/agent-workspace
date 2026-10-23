"""Provide persistence queries owned by the chat slice."""

import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.database.models import Conversation, User


class ConversationRepository:
    """Read conversations through user and agent ownership boundaries."""

    def __init__(self, session: AsyncSession) -> None:
        """Bind conversation lookups to one database session."""
        self.session = session

    async def get_owned(self, conversation_id: uuid.UUID, user: User) -> Conversation:
        """Return a conversation only when it belongs to the supplied user and agent."""
        conversation = await self.session.scalar(
            select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.user_id == user.id,
                Conversation.agent_id == user.agent_id,
            )
        )
        if conversation is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return conversation


async def owned_conversation(
    conversation_id: uuid.UUID, user: User, session: AsyncSession
) -> Conversation:
    """Resolve a conversation through its ownership boundary."""
    return await ConversationRepository(session).get_owned(conversation_id, user)
