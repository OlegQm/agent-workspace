"""Manage the browser cookie that carries an opaque login-session token."""

from fastapi import Response

from infrastructure.settings import settings

COOKIE_NAME = "open-agent-workspace_ai_session"


def set_session_cookie(response: Response, token: str) -> None:
    """Set the hardened login-session cookie."""
    response.set_cookie(
        COOKIE_NAME,
        token,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="strict",
        max_age=settings.session_ttl_hours * 3600,
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    """Expire the login-session cookie."""
    response.delete_cookie(
        COOKIE_NAME,
        path="/",
        secure=settings.session_cookie_secure,
        samesite="strict",
    )
