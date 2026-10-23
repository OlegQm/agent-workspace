"""Test asynchronous database session configuration."""

from infrastructure.database import session


def test_session_factory_uses_shared_engine_without_expiring_records() -> None:
    """Bind sessions to the configured engine and preserve records after commits."""
    assert session.SessionLocal.kw["bind"] is session.engine
    assert session.SessionLocal.kw["expire_on_commit"] is False
