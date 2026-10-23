"""Handle login, logout, and current-session HTTP operations."""

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from features.identity.api.cookies import COOKIE_NAME, clear_session_cookie, set_session_cookie
from features.identity.api.dependencies import current_user, get_db
from features.identity.api.presenters import serialize_user
from features.identity.api.schemas import LoginBody
from features.identity.application.authentication import (
    authenticate,
    create_login_session,
    hash_token,
)
from infrastructure.database.models import LoginSession, User
from infrastructure.settings import settings

router = APIRouter()


@router.post("/api/auth/login")
async def login(body: LoginBody, response: Response, session: AsyncSession = Depends(get_db)):
    """Authenticate the requested data."""
    user = await authenticate(session, body.username, body.password)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token, login_session = await create_login_session(session, user, settings.session_ttl_hours)
    set_session_cookie(response, token)
    return {"user": serialize_user(user), "expires_at": login_session.expires_at}


@router.post("/api/auth/logout", status_code=204)
async def logout(request: Request, response: Response, session: AsyncSession = Depends(get_db)):
    """End the requested data."""
    token = request.cookies.get(COOKIE_NAME)
    if token:
        await session.execute(
            delete(LoginSession).where(LoginSession.token_hash == hash_token(token))
        )
        await session.commit()
    clear_session_cookie(response)


@router.get("/api/auth/me")
async def me(user: User = Depends(current_user)):
    """Handle me."""
    return serialize_user(user)


@router.post("/api/auth/refresh")
async def refresh_session(user: User = Depends(current_user)):
    """Refresh session."""
    return {"status": "ok", "user_id": str(user.id)}
