"""Test idempotent schema compatibility statements."""

import pytest

from infrastructure.database.migrations.schema import apply_schema_compatibility


@pytest.mark.unit
async def test_schema_compatibility_executes_all_fixed_statements() -> None:
    """Apply every compatibility statement through the supplied connection."""
    statements: list[str] = []

    class Connection:
        """Record SQLAlchemy statements without opening a database connection."""

        async def execute(self, statement) -> None:
            """Capture a compiled text statement."""
            statements.append(str(statement))

    await apply_schema_compatibility(Connection())

    assert len(statements) == 8
    assert any("ADD COLUMN IF NOT EXISTS is_admin" in statement for statement in statements)
    assert any("hermes_session_id" in statement for statement in statements)
    assert any("ix_conversation_runtimes_hermes_session_id" in statement for statement in statements)
