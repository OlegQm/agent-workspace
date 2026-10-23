"""Provide shared application fixtures for endpoint characterization tests."""

from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from bootstrap import app as application
from features.agents.api import router as health_api
from features.chat.api import router as conversations_api
from features.identity.api import presenters as identity_serializers
from features.identity.application.authentication import password_hash
from features.workspace.api import admin_router as admin_api
from features.workspace.api import user_router as workspace_api
from infrastructure.database.models import User
from tests.support.llm import configured_llm_profile


def agent(workspace: Path) -> SimpleNamespace:
    """Return a complete fake agent for isolated endpoint characterization tests."""
    return SimpleNamespace(
        id="assistant",
        display_name="Assistant",
        tools=["metabase", "code"],
        hermes_url="http://hermes.invalid",
        hermes_api_key="test-key",
        workspace_root=workspace,
        instructions="Test instructions",
        llm=configured_llm_profile(),
    )


@pytest.fixture
def configured_agent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """Configure every agent lookup to use a temporary workspace."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    configured = agent(workspace)
    for module in (
        health_api,
        conversations_api,
        identity_serializers,
        workspace_api,
        admin_api,
    ):
        monkeypatch.setattr(module, "get_agent", lambda _: configured)
    monkeypatch.setattr(
        application.app.state.container,
        "agent_loader",
        lambda: {"assistant": configured},
    )
    return configured


@pytest.fixture
async def users(database, configured_agent: SimpleNamespace) -> tuple[User, User]:
    """Create one regular Assistant user and one administrator."""
    regular = User(
        username="assistant-user",
        password_hash=password_hash.hash("correct horse battery staple"),
        agent_id="assistant",
        locale="en",
    )
    administrator = User(
        username="administrator",
        password_hash=password_hash.hash("correct horse battery staple"),
        locale="en",
        is_admin=True,
    )
    async with database() as session:
        session.add_all([regular, administrator])
        await session.commit()
        await session.refresh(regular)
        await session.refresh(administrator)
    return regular, administrator


async def login(client: httpx.AsyncClient, username: str) -> None:
    """Authenticate a fixture user through the public API."""
    response = await client.post(
        "/api/auth/login",
        json={"username": username, "password": "correct horse battery staple"},
    )
    assert response.status_code == 200
