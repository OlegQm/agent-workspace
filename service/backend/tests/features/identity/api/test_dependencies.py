"""Test identity and role-based HTTP dependencies."""

import pytest
from fastapi import HTTPException, Request, Response

from features.identity.api import cookies, dependencies
from features.identity.application.authentication import create_login_session
from infrastructure.database.models import User
from infrastructure.settings import settings


@pytest.mark.asyncio
async def test_admin_access_depends_on_flag_not_username() -> None:
    """Verify that administrator authorization does not reserve a username."""
    administrator = User(
        username="workspace-owner",
        password_hash="unused",
        agent_id=None,
        locale="en",
        is_admin=True,
    )
    regular_named_admin = User(
        username="admin",
        password_hash="unused",
        agent_id="assistant",
        locale="en",
        is_admin=False,
    )

    assert await dependencies.admin_user(administrator) is administrator
    with pytest.raises(HTTPException) as exc_info:
        await dependencies.admin_user(regular_named_admin)
    assert exc_info.value.status_code == 403


@pytest.mark.integration
async def test_current_user_resolution_refresh_and_rejections(database) -> None:
    """Preserve cookie authentication, renewal, and invalid-session rejection."""
    async with database() as session:
        user = User(username="regular", password_hash="unused", agent_id="assistant")
        session.add(user)
        await session.commit()
        await session.refresh(user)
        token, _login = await create_login_session(session, user, 1)
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [(b"cookie", f"{cookies.COOKIE_NAME}={token}".encode())],
        }
        response = Response()
        loaded = await dependencies.current_user(Request(scope), response, session)
        assert loaded.id == user.id
        assert await dependencies.agent_user(loaded) is loaded

        with pytest.raises(HTTPException) as missing:
            await dependencies.current_user(Request({**scope, "headers": []}), Response(), session)
        assert missing.value.status_code == 401
        invalid_scope = {
            **scope,
            "headers": [(b"cookie", f"{cookies.COOKIE_NAME}=invalid".encode())],
        }
        with pytest.raises(HTTPException) as invalid:
            await dependencies.current_user(Request(invalid_scope), Response(), session)
        assert invalid.value.status_code == 401


@pytest.mark.integration
async def test_current_user_does_not_refresh_a_recent_session(database) -> None:
    """Preserve the no-write path for sessions outside the refresh window."""
    async with database() as session:
        user = User(username="recent", password_hash="unused", agent_id="assistant")
        session.add(user)
        await session.commit()
        await session.refresh(user)
        token, login = await create_login_session(session, user, settings.session_ttl_hours * 2)
        original_expiry = login.expires_at
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [(b"cookie", f"{cookies.COOKIE_NAME}={token}".encode())],
        }

        response = Response()
        assert (await dependencies.current_user(Request(scope), response, session)).id == user.id
        assert login.expires_at == original_expiry
        assert cookies.COOKIE_NAME not in response.headers.get("set-cookie", "")


@pytest.mark.asyncio
async def test_auth_role_guards_reject_incorrect_roles() -> None:
    """Preserve explicit regular-user and administrator dependency rejections."""
    administrator = User(username="owner", password_hash="unused", is_admin=True)
    missing_agent = User(username="missing", password_hash="unused", is_admin=False)
    with pytest.raises(HTTPException):
        await dependencies.agent_user(administrator)
    with pytest.raises(HTTPException):
        await dependencies.agent_user(missing_agent)
    with pytest.raises(HTTPException):
        await dependencies.admin_user(missing_agent)
