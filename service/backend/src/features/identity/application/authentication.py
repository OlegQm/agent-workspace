"""Authenticate users and manage renewable server-side sessions."""

import hashlib
import secrets
from datetime import datetime, timedelta

from pwdlib import PasswordHash
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.database.models import LoginSession, User, utcnow
from infrastructure.settings import settings

password_hash = PasswordHash.recommended()
DUMMY_PASSWORD_HASH = password_hash.hash(secrets.token_urlsafe(48))


class AuthenticationService:
    """Authenticate users and manage persisted login sessions."""

    def __init__(self, session: AsyncSession) -> None:
        """Bind authentication operations to one database session."""
        self.session = session

    async def authenticate(self, username: str, password: str) -> User | None:
        """Authenticate without exposing username existence through hash timing."""
        user = await self.session.scalar(
            select(User).where(User.username == username, User.is_active.is_(True))
        )
        encoded = user.password_hash if user is not None else DUMMY_PASSWORD_HASH
        valid = password_hash.verify(password, encoded)
        if user is None or not valid:
            return None
        return user

    async def create_login_session(self, user: User, ttl_hours: int) -> tuple[str, LoginSession]:
        """Create a renewable opaque login session for a user."""
        await self.session.execute(delete(LoginSession).where(LoginSession.expires_at <= utcnow()))
        token = secrets.token_urlsafe(48)
        login = LoginSession(
            user_id=user.id,
            token_hash=hash_token(token),
            expires_at=utcnow() + timedelta(hours=ttl_hours),
        )
        self.session.add(login)
        await self.session.commit()
        return token, login

    async def resolve_login(self, token: str, now: datetime) -> tuple[User, LoginSession] | None:
        """Resolve an active user and login session from an opaque token."""
        return (
            await self.session.execute(
                select(User, LoginSession)
                .join(LoginSession, LoginSession.user_id == User.id)
                .where(
                    LoginSession.token_hash == hash_token(token),
                    LoginSession.expires_at > now,
                    User.is_active.is_(True),
                )
            )
        ).one_or_none()

    async def refresh_login(self, login: LoginSession, now: datetime) -> None:
        """Extend a login session using the configured application TTL."""
        login.expires_at = now + timedelta(hours=settings.session_ttl_hours)
        await self.session.commit()


def hash_token(token: str) -> str:
    """Hash an opaque session token for persistent storage."""
    return hashlib.sha256(token.encode()).hexdigest()


def session_needs_refresh(expires_at: datetime, now: datetime) -> bool:
    """Return whether a session has entered its configured refresh window."""
    refresh_before = now + timedelta(
        hours=settings.session_ttl_hours,
        seconds=-settings.session_refresh_interval_seconds,
    )
    return expires_at <= refresh_before


async def authenticate(session: AsyncSession, username: str, password: str) -> User | None:
    """Authenticate a user through the session-bound application service."""
    return await AuthenticationService(session).authenticate(username, password)


async def create_login_session(
    session: AsyncSession, user: User, ttl_hours: int
) -> tuple[str, LoginSession]:
    """Create a login through the session-bound application service."""
    return await AuthenticationService(session).create_login_session(user, ttl_hours)
