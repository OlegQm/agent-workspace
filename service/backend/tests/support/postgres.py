"""Create an isolated PostgreSQL database for integration tests."""

from collections.abc import Iterator

import pytest
from testcontainers.community.postgres import PostgresContainer


@pytest.fixture(scope="session")
def postgres_dsn() -> Iterator[str]:
    """Yield an async SQLAlchemy URL backed by PostgreSQL 17 in Docker."""
    try:
        with PostgresContainer("postgres:17-alpine", driver="asyncpg") as container:
            yield container.get_connection_url()
    except Exception as exc:
        pytest.skip(f"PostgreSQL test container is unavailable: {exc}")
