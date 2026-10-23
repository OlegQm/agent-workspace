"""Test validated HTTP payloads owned by the identity slice."""

import pytest
from pydantic import ValidationError

from features.identity.api.schemas import LoginBody


def test_login_body_accepts_bounded_credentials() -> None:
    """Verify that a valid login payload preserves its credentials."""
    body = LoginBody(username="assistant-user", password="correct horse battery staple")

    assert body.username == "assistant-user"
    assert body.password == "correct horse battery staple"


@pytest.mark.parametrize("username,password", [("", "password"), ("user", "")])
def test_login_body_rejects_empty_credentials(username: str, password: str) -> None:
    """Verify that login payloads require both username and password."""
    with pytest.raises(ValidationError):
        LoginBody(username=username, password=password)
