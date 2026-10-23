"""Test idempotent database data cleanup."""

import pytest

from infrastructure.database.migrations.data import remove_empty_conversations


@pytest.mark.unit
async def test_empty_conversation_cleanup_uses_fixed_guarded_delete() -> None:
    """Delete only empty placeholder conversations through the supplied connection."""
    statements: list[str] = []

    class Connection:
        """Record SQLAlchemy statements without opening a database connection."""

        async def execute(self, statement) -> None:
            """Capture a compiled text statement."""
            statements.append(str(statement))

    await remove_empty_conversations(Connection())

    assert len(statements) == 1
    assert "conversation.title = 'New conversation'" in statements[0]
    assert "NOT EXISTS" in statements[0]
    assert "messages.conversation_id" in statements[0]
    assert "agent_runs.conversation_id" in statements[0]
