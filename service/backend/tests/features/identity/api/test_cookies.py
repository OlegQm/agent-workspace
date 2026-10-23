"""Test hardened identity cookies."""

from fastapi import Response

from features.identity.api import cookies


def test_session_cookie_creation_and_removal() -> None:
    """Preserve cookie creation and expiry attributes."""
    response = Response()
    cookies.set_session_cookie(response, "opaque-token")
    assert cookies.COOKIE_NAME in response.headers["set-cookie"]

    cookies.clear_session_cookie(response)
    assert any("max-age=0" in value.lower() for value in response.headers.getlist("set-cookie"))
