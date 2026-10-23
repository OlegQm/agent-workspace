"""Provide identity and authorization dependencies for HTTP endpoints."""

from fastapi import Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from features.identity.api.cookies import COOKIE_NAME, set_session_cookie
from features.identity.application.authentication import (
    AuthenticationService,
    session_needs_refresh,
)
from infrastructure.database.models import User, utcnow
from infrastructure.database.session import SessionLocal


async def get_db():
    """Yield one database session for an HTTP request."""
    async with SessionLocal() as session:
        yield session


async def current_user(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_db),
) -> User:
    """Resolve the current user and refresh an aging valid login session."""
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    now = utcnow()
    service = AuthenticationService(session)
    row = await service.resolve_login(token, now)
    if row is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    user, login_session = row
    if session_needs_refresh(login_session.expires_at, now):
        await service.refresh_login(login_session, now)
        set_session_cookie(response, token)
    return user


async def agent_user(user: User = Depends(current_user)) -> User:
    """Require a regular user assigned to an agent workspace."""
    if user.is_admin or not user.agent_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Agent access required")
    return user


async def admin_user(user: User = Depends(current_user)) -> User:
    """Require an account with administrator privileges."""
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Administrator access required"
        )
    return user
