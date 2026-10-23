"""Test database initialization and compatibility operations."""

import pytest
from sqlalchemy import inspect, select, text

from infrastructure.database import initialization
from infrastructure.database.initialization import DatabaseInitializer, _has_missing_model_columns
from infrastructure.database.models import Conversation, User


@pytest.mark.unit
def test_schema_shape_check_ignores_tables_not_created_yet(monkeypatch) -> None:
    """Let create-all own canonical tables that do not exist yet."""
    class Inspector:
        """Represent an empty schema inspector."""

        @staticmethod
        def get_table_names() -> list[str]:
            """Return no initialized tables."""
            return []

    monkeypatch.setattr(initialization, "inspect", lambda _: Inspector())
    assert _has_missing_model_columns(object()) is False


@pytest.mark.integration
async def test_initialize_database_is_idempotent_and_removes_empty_placeholders(database) -> None:
    """Preserve startup schema compatibility statements and empty-chat cleanup."""
    async with database() as session:
        user = User(username="cleanup", password_hash="unused", agent_id="assistant")
        session.add(user)
        await session.flush()
        session.add(Conversation(user_id=user.id, agent_id="assistant", title="New conversation"))
        await session.commit()

    await initialization.initialize_database()

    async with database() as session:
        assert (await session.scalars(select(Conversation))).all() == []


@pytest.mark.integration
async def test_development_initializer_recreates_an_incompatible_disposable_schema(database) -> None:
    """Recreate all tables instead of carrying feature-specific compatibility SQL."""
    async with database() as session:
        user = User(username="discarded", password_hash="unused", agent_id="assistant")
        session.add(user)
        await session.commit()

    async with initialization.engine.begin() as connection:
        await connection.execute(text("ALTER TABLE conversations DROP COLUMN kind"))

    await DatabaseInitializer(initialization.engine, allow_destructive_reset=True).initialize()

    async with initialization.engine.connect() as connection:
        columns = await connection.run_sync(
            lambda sync: {column["name"] for column in inspect(sync).get_columns("conversations")}
        )
    async with database() as session:
        assert "kind" in columns
        assert (await session.scalars(select(User))).all() == []


@pytest.mark.integration
async def test_production_initializer_refuses_an_incompatible_schema(database) -> None:
    """Fail closed instead of destructively changing an incompatible durable database."""
    async with initialization.engine.begin() as connection:
        await connection.execute(text("ALTER TABLE conversations DROP COLUMN kind"))

    with pytest.raises(RuntimeError, match="incompatible"):
        await DatabaseInitializer(initialization.engine, allow_destructive_reset=False).initialize()
