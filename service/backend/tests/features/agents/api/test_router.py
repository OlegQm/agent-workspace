"""Test the agent health capability endpoint."""

from types import SimpleNamespace

import httpx
import pytest
import respx
from support.application import login

from bootstrap import app as application
from features.agents.api import router as health_api
from features.chat.infrastructure.hermes.runtime import (
    REQUIRED_HERMES_ENDPOINTS,
    REQUIRED_HERMES_FEATURES,
)
from infrastructure.database.models import User


@pytest.mark.integration
async def test_healthz_contract() -> None:
    """Verify that the unauthenticated process health endpoint remains available."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application.app), base_url="http://localhost"
    ) as client:
        response = await client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.integration
@respx.mock
async def test_health_runtime_status_contracts(
    users: tuple[User, User], configured_agent: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify health statuses for compatible and failing Hermes runtimes."""
    configured_agent.hermes_url = "http://health-hermes.test"
    capability = {
        "features": {name: True for name in REQUIRED_HERMES_FEATURES},
        "endpoints": {name: {} for name in REQUIRED_HERMES_ENDPOINTS},
    }
    monkeypatch.setattr(health_api, "hermes_headers", lambda _: {"Authorization": "Bearer test"})
    route = respx.get("http://health-hermes.test/v1/capabilities")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application.app), base_url="http://localhost"
    ) as client:
        await login(client, "assistant-user")
        route.mock(return_value=httpx.Response(200, json=capability))
        assert (await client.get("/api/health")).json()["hermes"] == "ok"
        route.mock(return_value=httpx.Response(500))
        assert (await client.get("/api/health")).json()["hermes"] == "error"
