"""Configure the test environment and shared fixtures."""

import os
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

pytest_plugins = ("support.application", "support.postgres")

os.environ.setdefault("APP_SECRET_KEY", "test-secret-key")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://test:test@127.0.0.1:5432/test",
)


@pytest.fixture
def agent_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    """Configure isolated manifest and agent-data paths for one test."""
    config_dir = tmp_path / "config" / "agents"
    data_dir = tmp_path / "data" / "agents"
    config_dir.mkdir(parents=True)
    data_dir.mkdir(parents=True)
    monkeypatch.setenv("AGENT_CONFIG_DIR", str(config_dir))
    monkeypatch.setenv("AGENT_DATA_DIR", str(data_dir))
    return config_dir, data_dir


@pytest_asyncio.fixture
async def database(
    postgres_dsn: str,
    monkeypatch: pytest.MonkeyPatch,
) -> async_sessionmaker:
    """Bind backend database globals to a clean PostgreSQL 17 schema for one test."""
    from bootstrap import app
    from bootstrap.container import ApplicationContainer
    from features.chat.infrastructure.hermes import runtime as hermes
    from features.identity.api import dependencies as identity_dependencies
    from infrastructure.database import initialization
    from infrastructure.database import models as db
    from infrastructure.database import session as db_session
    from infrastructure.database.initialization import DatabaseInitializer
    from infrastructure.settings import settings

    engine: AsyncEngine = create_async_engine(postgres_dsn, pool_pre_ping=True)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(db_session, "engine", engine)
    monkeypatch.setattr(db_session, "SessionLocal", sessions)
    monkeypatch.setattr(initialization, "engine", engine)
    monkeypatch.setattr(identity_dependencies, "SessionLocal", sessions)
    monkeypatch.setattr(
        app.app.state,
        "container",
        ApplicationContainer(
            settings=settings,
            session_factory=sessions,
            agent_loader=dict,
            database_initializer=DatabaseInitializer(engine),
        ),
    )
    monkeypatch.setattr(hermes, "SessionLocal", sessions)
    async with engine.begin() as connection:
        await connection.run_sync(db.Base.metadata.drop_all)
        await connection.run_sync(db.Base.metadata.create_all)
    try:
        yield sessions
    finally:
        await engine.dispose()
