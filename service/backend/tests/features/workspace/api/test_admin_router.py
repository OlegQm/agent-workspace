"""Test the administrator workspace and read-only conversation API."""

import base64
from types import SimpleNamespace

import httpx
import pytest
from openpyxl import Workbook
from support.application import login

from bootstrap import app as application
from features.workspace.api import admin_router as admin_api
from infrastructure.database.models import AgentRun, Conversation, Message, RunStatus, User
from infrastructure.settings import settings


@pytest.mark.unit
def test_admin_conversation_routes_are_get_only() -> None:
    """Verify that administrative conversation history routes remain read-only."""
    route_methods = {
        route.path: route.methods
        for route in application.app.routes
        if route.path.startswith("/api/admin/users/{user_id}/conversations")
    }

    assert route_methods == {
        "/api/admin/users/{user_id}/conversations": {"GET"},
        "/api/admin/users/{user_id}/conversations/{conversation_id}": {"GET"},
        "/api/admin/users/{user_id}/conversations/{conversation_id}/export": {"GET"},
    }


@pytest.mark.integration
@pytest.mark.contract
async def test_administrator_downloads_complete_conversation_json(
    users: tuple[User, User],
    database,
) -> None:
    """Return a real JSON attachment containing the selected user's complete dialog."""
    async with database() as session:
        conversation = Conversation(user_id=users[0].id, agent_id="assistant", title="Export me")
        session.add(conversation)
        await session.flush()
        session.add(
            Message(
                conversation_id=conversation.id,
                role="user",
                content="What was July revenue?",
                attachments=["reports/july.xlsx"],
            )
        )
        session.add(
            AgentRun(
                conversation_id=conversation.id,
                user_id=users[0].id,
                agent_id="assistant",
                status=RunStatus.completed.value,
            )
        )
        await session.commit()
        await session.refresh(conversation)

    url = f"/api/admin/users/{users[0].id}/conversations/{conversation.id}/export"
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application.app), base_url="http://localhost"
    ) as client:
        await login(client, "administrator")
        response = await client.get(url)

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    assert response.headers["content-disposition"] == (
        f'attachment; filename="conversation-{conversation.id}.json"'
    )
    assert response.json() == {
        "id": str(conversation.id),
        "title": "Export me",
        "kind": "standard",
        "created_at": conversation.created_at.isoformat(),
        "updated_at": conversation.updated_at.isoformat(),
        "messages": [
            {
                "id": response.json()["messages"][0]["id"],
                "role": "user",
                "content": "What was July revenue?",
                "attachments": ["reports/july.xlsx"],
                "created_at": response.json()["messages"][0]["created_at"],
            }
        ],
        "runs": [
            {
                "id": response.json()["runs"][0]["id"],
                "conversation_id": str(conversation.id),
                "status": "completed",
                "model_mode": "medium",
                "error": None,
                "created_at": response.json()["runs"][0]["created_at"],
                "updated_at": response.json()["runs"][0]["updated_at"],
            }
        ],
    }


@pytest.mark.integration
async def test_regular_user_cannot_export_conversation_json(
    users: tuple[User, User],
    database,
) -> None:
    """Reject conversation export before exposing any managed-user data to a regular user."""
    async with database() as session:
        conversation = Conversation(user_id=users[0].id, agent_id="assistant", title="Private")
        session.add(conversation)
        await session.commit()
        await session.refresh(conversation)

    url = f"/api/admin/users/{users[0].id}/conversations/{conversation.id}/export"
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application.app), base_url="http://localhost"
    ) as client:
        await login(client, "assistant-user")
        response = await client.get(url)

    assert response.status_code == 403
    assert response.json() == {"detail": "Administrator access required"}


@pytest.mark.integration
async def test_administrator_cannot_export_conversation_outside_managed_user(
    users: tuple[User, User],
    database,
) -> None:
    """Return no conversation data when the requested user does not own the dialog."""
    async with database() as session:
        other_user = User(username="other-user", password_hash="unused", agent_id="other-agent")
        session.add(other_user)
        await session.flush()
        conversation = Conversation(user_id=other_user.id, agent_id="other-agent", title="Other")
        session.add(conversation)
        await session.commit()
        await session.refresh(conversation)

    url = f"/api/admin/users/{users[0].id}/conversations/{conversation.id}/export"
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application.app), base_url="http://localhost"
    ) as client:
        await login(client, "administrator")
        response = await client.get(url)

    assert response.status_code == 404
    assert response.json() == {"detail": "Conversation not found"}


@pytest.mark.integration
@pytest.mark.contract
async def test_admin_workspace_and_read_only_history_contract(
    users: tuple[User, User], configured_agent: SimpleNamespace, database
) -> None:
    """Verify administrator file management and read-only conversation inspection APIs."""
    configured_agent.workspace_root.joinpath("admin.txt").write_text("admin")
    async with database() as session:
        conversation = Conversation(user_id=users[0].id, agent_id="assistant", title="Saved")
        session.add(conversation)
        await session.flush()
        session.add(
            AgentRun(
                conversation_id=conversation.id,
                user_id=users[0].id,
                agent_id="assistant",
                status=RunStatus.completed.value,
            )
        )
        await session.commit()
        await session.refresh(conversation)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application.app), base_url="http://localhost"
    ) as client:
        await login(client, "administrator")
        target = str(users[0].id)
        assert (await client.get("/api/admin/users")).json() == [
            {
                "id": target,
                "username": "assistant-user",
                "agent_id": "assistant",
                "agent_name": "Assistant",
                "locale": "en",
                "is_active": True,
            }
        ]
        listed = await client.get(f"/api/admin/users/{target}/files")
        assert listed.status_code == 200
        assert listed.json()["entries"][0]["can_modify"] is True
        assert (
            await client.post(f"/api/admin/users/{target}/files/folder", json={"path": "managed"})
        ).status_code == 201
        assert (
            await client.post(
                f"/api/admin/users/{target}/files/upload",
                data={"path": "managed"},
                files={"upload": ("notes.txt", b"notes", "text/plain")},
            )
        ).status_code == 201
        assert (
            await client.patch(
                f"/api/admin/users/{target}/files",
                json={"path": "managed/notes.txt", "new_name": "renamed.txt"},
            )
        ).json() == {"path": "managed/renamed.txt"}
        assert (
            await client.delete(
                f"/api/admin/users/{target}/files", params={"path": "managed/renamed.txt"}
            )
        ).status_code == 204
        conversations = await client.get(f"/api/admin/users/{target}/conversations")
        assert conversations.status_code == 200
        assert (
            await client.get(f"/api/admin/users/{target}/conversations/{conversation.id}")
        ).json()["title"] == "Saved"
        assert (
            await client.get(
                f"/api/admin/users/{target}/files/download", params={"path": "admin.txt"}
            )
        ).content == b"admin"


@pytest.mark.integration
async def test_administrator_access_policy_contract(
    users: tuple[User, User],
    configured_agent: SimpleNamespace,
    database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that administrators can set and remove an existing workspace access policy."""
    workbook = Workbook()
    workbook.save(configured_agent.workspace_root / "report.xlsx")
    configured_agent.workspace_root.joinpath("notes.txt").write_text("Managed notes")
    configured_agent.workspace_root.joinpath("chart.png").write_bytes(
        base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
        )
    )
    monkeypatch.setattr(
        settings,
        "preview_cache_dir",
        configured_agent.workspace_root.parent / "preview-cache",
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application.app), base_url="http://localhost"
    ) as client:
        await login(client, "administrator")
        target = str(users[0].id)
        access = await client.put(
            f"/api/admin/users/{target}/files/access",
            json={"path": "report.xlsx", "no_user_access": True},
        )
        assert access.json() == {"path": "report.xlsx", "no_user_access": True}
        for previewable in ("notes.txt", "chart.png"):
            response = await client.put(
                f"/api/admin/users/{target}/files/access",
                json={"path": previewable, "no_user_access": True},
            )
            assert response.status_code == 200
        image = await client.get(
            f"/api/admin/users/{target}/files/preview/image",
            params={"path": "chart.png"},
        )
        assert image.status_code == 200
        assert image.headers["content-type"] == "image/png"
        async with database() as session:
            direct_image = await admin_api.admin_preview_image(
                users[0].id,
                "chart.png",
                users[1],
                session,
            )
            assert direct_image.media_type == "image/png"
        assert (
            await client.put(
                f"/api/admin/users/{target}/files/access",
                json={"path": "report.xlsx", "no_user_access": False},
            )
        ).status_code == 200
        assert (
            await client.put(
                f"/api/admin/users/{target}/files/access",
                json={"path": "missing.txt", "no_user_access": True},
            )
        ).status_code == 404
