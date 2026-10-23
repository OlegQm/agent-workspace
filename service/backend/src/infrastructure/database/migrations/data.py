"""Apply idempotent data cleanup operations."""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection


async def remove_empty_conversations(connection: AsyncConnection) -> None:
    """Remove empty placeholder conversations left by earlier clients."""
    await connection.execute(
        text(
            "DELETE FROM conversations AS conversation "
            "WHERE conversation.title = 'New conversation' "
            "AND NOT EXISTS ("
            "SELECT 1 FROM messages WHERE messages.conversation_id = conversation.id"
            ") AND NOT EXISTS ("
            "SELECT 1 FROM agent_runs WHERE agent_runs.conversation_id = conversation.id"
            ")"
        )
    )
