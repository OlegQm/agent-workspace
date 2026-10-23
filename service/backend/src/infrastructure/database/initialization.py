"""Initialize the database schema and runtime compatibility state."""

from dataclasses import dataclass

from sqlalchemy import inspect
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncEngine

from infrastructure.database import models
from infrastructure.database.migrations.data import remove_empty_conversations
from infrastructure.database.migrations.schema import apply_schema_compatibility
from infrastructure.database.session import engine
from infrastructure.settings import settings


def _has_missing_model_columns(connection: Connection) -> bool:
    """Return whether an existing table lacks any column in the canonical model."""
    inspector = inspect(connection)
    existing_tables = set(inspector.get_table_names())
    for table in models.Base.metadata.sorted_tables:
        if table.name not in existing_tables:
            continue
        actual = {column["name"] for column in inspector.get_columns(table.name)}
        if {column.name for column in table.columns} - actual:
            return True
    return False


@dataclass(frozen=True)
class DatabaseInitializer:
    """Apply database initialization through an injected asynchronous engine."""

    engine: AsyncEngine
    allow_destructive_reset: bool = False

    async def initialize(self) -> None:
        """Create the canonical schema or recreate an incompatible disposable schema."""
        async with self.engine.begin() as connection:
            await connection.run_sync(models.Base.metadata.create_all)
            await apply_schema_compatibility(connection)
            incompatible = await connection.run_sync(_has_missing_model_columns)
            if incompatible and not self.allow_destructive_reset:
                raise RuntimeError(
                    "Database schema is incompatible; an explicit destructive reset is required"
                )
            if incompatible:
                await connection.run_sync(models.Base.metadata.drop_all)
                await connection.run_sync(models.Base.metadata.create_all)
            await remove_empty_conversations(connection)


async def initialize_database() -> None:
    """Initialize the default application database."""
    await DatabaseInitializer(
        engine,
        allow_destructive_reset=settings.app_env != "production",
    ).initialize()
