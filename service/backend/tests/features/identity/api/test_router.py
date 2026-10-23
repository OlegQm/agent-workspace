"""Test HTTP session endpoints owned by the identity API."""

from types import SimpleNamespace

import httpx
import pytest
from support.application import login

from bootstrap import app as application
from infrastructure.database.models import User


@pytest.mark.integration
@pytest.mark.contract
async def test_session_http_contract(
    users: tuple[User, User], configured_agent: SimpleNamespace
) -> None:
    """Verify login, authenticated user metadata, logout, and unauthenticated rejection."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application.app), base_url="http://localhost"
    ) as client:
        denied = await client.get("/api/auth/me")
        assert denied.status_code == 401
        assert denied.headers["cache-control"] == "no-store, private"
        assert denied.headers["x-frame-options"] == "DENY"

        await login(client, "assistant-user")
        me = await client.get("/api/auth/me")
        assert me.json() == {
            "id": str(users[0].id),
            "username": "assistant-user",
            "agent_id": "assistant",
            "agent_name": "Assistant",
            "locale": "en",
            "tools": ["metabase", "code"],
            "model_modes": configured_agent.llm.public_mode_descriptors(),
            "default_model_mode": "medium",
            "is_admin": False,
        }
        assert (await client.post("/api/auth/logout")).status_code == 204
        assert (await client.get("/api/auth/me")).status_code == 401
