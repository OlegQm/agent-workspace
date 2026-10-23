"""Apply idempotent schema compatibility operations."""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection


async def apply_schema_compatibility(connection: AsyncConnection) -> None:
    """Apply schema statements required by existing installations."""
    await connection.execute(
        text("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_admin BOOLEAN NOT NULL DEFAULT false")
    )
    await connection.execute(text("ALTER TABLE users ALTER COLUMN agent_id DROP NOT NULL"))
    await connection.execute(
        text(
            "ALTER TABLE agent_runs "
            "ADD COLUMN IF NOT EXISTS model_mode VARCHAR(16) NOT NULL DEFAULT 'medium'"
        )
    )
    await connection.execute(
        text("ALTER TABLE agent_runs ALTER COLUMN model_mode SET DEFAULT 'medium'")
    )
    await connection.execute(
        text(
            "ALTER TABLE agent_runs "
            "ADD COLUMN IF NOT EXISTS finalized BOOLEAN NOT NULL DEFAULT false"
        )
    )
    await connection.execute(
        text(
            "ALTER TABLE conversation_runtimes "
            "ADD COLUMN IF NOT EXISTS hermes_session_id VARCHAR(128)"
        )
    )
    await connection.execute(
        text(
            "ALTER TABLE conversation_runtimes ADD COLUMN IF NOT EXISTS initialized_at TIMESTAMPTZ"
        )
    )
    await connection.execute(
        text(
            "CREATE UNIQUE INDEX IF NOT EXISTS "
            "ix_conversation_runtimes_hermes_session_id "
            "ON conversation_runtimes (hermes_session_id) "
            "WHERE hermes_session_id IS NOT NULL"
        )
    )
