"""Test identity authentication services."""

from datetime import timedelta

import pytest
from sqlalchemy import select

from features.identity.application import authentication
from infrastructure.database.models import LoginSession, User, utcnow
from infrastructure.settings import settings


def test_session_refresh_is_throttled() -> None:
    """Verify that session refresh is throttled."""
    now = utcnow()
    full_ttl = timedelta(hours=settings.session_ttl_hours)
    interval = timedelta(seconds=settings.session_refresh_interval_seconds)

    assert not authentication.session_needs_refresh(now + full_ttl, now)
    assert authentication.session_needs_refresh(now + full_ttl - interval, now)


@pytest.mark.integration
async def test_authentication_and_login_session_persistence(database) -> None:
    """Preserve password verification and persisted opaque login sessions."""
    async with database() as session:
        user = User(
            username="regular",
            password_hash=authentication.password_hash.hash("a sufficiently long password"),
            agent_id="assistant",
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

        assert (
            await authentication.authenticate(session, "regular", "a sufficiently long password")
            is user
        )
        assert await authentication.authenticate(session, "missing", "wrong") is None
        token, login = await authentication.create_login_session(session, user, 1)
        assert login.token_hash == authentication.hash_token(token)
        assert (await session.scalars(select(LoginSession))).first() is not None
