"""Test database models behavior."""

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine

from infrastructure.database.models import Conversation, ConversationRuntime


def test_conversation_messages_are_deleted_with_conversation() -> None:
    """Verify that conversation messages are deleted with conversation."""
    relationship = inspect(Conversation).relationships.messages

    assert relationship.passive_deletes is True
    assert "delete" in relationship.cascade
    assert "delete-orphan" in relationship.cascade


def test_conversation_runtime_is_deleted_with_conversation() -> None:
    """Verify that conversation runtime is deleted with conversation."""
    relationship = inspect(Conversation).relationships.runtime

    assert relationship.passive_deletes is True
    assert relationship.uselist is False
    assert "delete" in relationship.cascade
    assert "delete-orphan" in relationship.cascade


def test_conversation_runtime_tracks_native_hermes_session() -> None:
    """Verify that runtime mappings store Hermes session initialization state."""
    columns = inspect(ConversationRuntime).columns

    assert "hermes_session_id" in columns
    assert columns.hermes_session_id.unique is True
    assert "initialized_at" in columns


@pytest.mark.integration
@pytest.mark.contract
async def test_schema_is_created_on_disposable_postgresql_17(postgres_dsn: str) -> None:
    """Verify the persisted schema against a real disposable PostgreSQL 17 instance."""
    from features.metabase_planning.infrastructure.persistence import models as planning_models
    from infrastructure.database.models import Base

    engine = create_async_engine(postgres_dsn)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
            table_names = {
                row[0]
                for row in (
                    await connection.execute(
                        text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
                    )
                ).all()
            }
            columns = {
                row[0]
                for row in (
                    await connection.execute(
                        text(
                            "SELECT column_name FROM information_schema.columns "
                            "WHERE table_name = 'conversation_runtimes'"
                        )
                    )
                ).all()
            }
    finally:
        await engine.dispose()

    assert table_names == {
        "agent_runs",
        "conversations",
        "conversation_runtimes",
        "login_sessions",
        "metabase_planning_operations",
        "metabase_planning_states",
        "messages",
        "run_events",
        "users",
        "workspace_path_policies",
    }
    assert {"conversation_id", "hermes_session_id", "initialized_at"} <= columns
    assert planning_models.MetabasePlanningState.__tablename__ in table_names
