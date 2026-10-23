"""Test HTTP conversation and run endpoints."""

import uuid
from types import SimpleNamespace

import httpx
import pytest
from fastapi import BackgroundTasks, HTTPException
from sqlalchemy import select
from support.application import login

from bootstrap import app as application
from features.chat.api import router as conversations_api
from features.chat.api import schemas as contracts
from infrastructure.database.models import (
    AgentRun,
    Conversation,
    ConversationRuntime,
    Message,
    RunStatus,
    User,
)


@pytest.mark.unit
async def test_standard_run_entrypoint_rejects_planning_kind(monkeypatch) -> None:
    """Require the specialized state-aware endpoint for planning corrections."""
    conversation = SimpleNamespace(kind="metabase_planning")

    async def owned(*_args):
        """Return one marked planning conversation."""
        return conversation

    monkeypatch.setattr(conversations_api, "owned_conversation", owned)
    with pytest.raises(HTTPException) as error:
        await conversations_api.start_run(
            uuid.uuid4(),
            SimpleNamespace(),
            BackgroundTasks(),
            SimpleNamespace(),
            SimpleNamespace(),
        )
    assert error.value.status_code == 409


@pytest.mark.integration
@pytest.mark.contract
async def test_conversation_contract_queues_one_run(
    users: tuple[User, User], configured_agent: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify new-conversation and persistent-session API response shapes."""

    async def compatible(_: str) -> None:
        """Pretend that the isolated Hermes runtime exposes every required capability."""

    async def do_not_execute(_: object) -> None:
        """Keep the contract test focused on run submission persistence."""

    monkeypatch.setattr(conversations_api, "ensure_hermes_session_capability", compatible)
    monkeypatch.setattr(conversations_api, "execute_run", do_not_execute)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application.app), base_url="http://localhost"
    ) as client:
        await login(client, "assistant-user")
        created = await client.post(
            "/api/conversations/runs",
            json={"content": "Remember this fact", "model_mode": "medium"},
        )
        assert created.status_code == 202
        body = created.json()
        assert body["conversation"]["title"] == "Remember this fact"
        assert body["run"]["status"] == "queued"
        assert body["run"]["model_mode"] == "medium"
        conversation_id = body["conversation"]["id"]
        detail = await client.get(f"/api/conversations/{conversation_id}")
        assert [item["role"] for item in detail.json()["messages"]] == ["user"]
        assert len(detail.json()["runs"]) == 1
        assert (await client.delete(f"/api/conversations/{conversation_id}")).status_code == 409


@pytest.mark.integration
async def test_omitted_mode_uses_agent_default(
    users: tuple[User, User], configured_agent: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Resolve omitted chat model mode from the selected agent's profile."""
    configured_agent.llm = configured_agent.llm.model_copy(update={"default_mode": "high"})

    async def compatible(_: str) -> None:
        """Avoid contacting Hermes during the API contract test."""

    monkeypatch.setattr(conversations_api, "ensure_hermes_session_capability", compatible)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application.app), base_url="http://localhost"
    ) as client:
        await login(client, "assistant-user")
        response = await client.post("/api/conversations/runs", json={"content": "Question"})

    assert response.status_code == 202
    assert response.json()["run"]["model_mode"] == "high"


@pytest.mark.integration
async def test_run_stop_and_approval_error_contracts(
    users: tuple[User, User], configured_agent: SimpleNamespace, database
) -> None:
    """Verify public run ownership, terminal stop, and approval validation responses."""
    async with database() as session:
        conversation = Conversation(user_id=users[0].id, agent_id="assistant", title="Question")
        session.add(conversation)
        await session.flush()
        run = AgentRun(
            conversation_id=conversation.id,
            user_id=users[0].id,
            agent_id="assistant",
            status=RunStatus.completed.value,
        )
        session.add(run)
        await session.commit()
        await session.refresh(run)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application.app), base_url="http://localhost"
    ) as client:
        await login(client, "assistant-user")
        assert (await client.get(f"/api/runs/{run.id}")).json()["status"] == "completed"
        assert (await client.post(f"/api/runs/{run.id}/stop")).json()["status"] == "completed"
        assert (
            await client.post(f"/api/runs/{run.id}/approval", json={"decision": "invalid"})
        ).status_code == 400
        assert (
            await client.post(f"/api/runs/{run.id}/approval", json={"decision": "once"})
        ).status_code == 409
        assert (
            await client.get(f"/api/runs/{run.id}/events", headers={"Last-Event-ID": "no"})
        ).status_code == 400


@pytest.mark.integration
async def test_direct_run_queue_and_deletion_contracts(
    users: tuple[User, User],
    configured_agent: SimpleNamespace,
    database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify attachment injection, queued state, and completed-chat deletion semantics."""
    configured_agent.workspace_root.joinpath("attachment.txt").write_text("input")

    async def compatible(_: str) -> None:
        """Provide a compatible runtime for isolated queue characterization."""

    async def no_execution(_: object) -> None:
        """Prevent the background job from using the network in this test."""

    async def no_session_delete(_: str, __: str) -> None:
        """Avoid a network call after the persistence behavior is verified."""

    monkeypatch.setattr(conversations_api, "ensure_hermes_session_capability", compatible)
    monkeypatch.setattr(conversations_api, "execute_run", no_execution)
    monkeypatch.setattr(conversations_api, "delete_hermes_session", no_session_delete)
    async with database() as session:
        conversation = Conversation(user_id=users[0].id, agent_id="assistant")
        session.add(conversation)
        await session.flush()
        session.add(
            ConversationRuntime(conversation_id=conversation.id, hermes_session_id="session_1")
        )
        await session.commit()
        run = await conversations_api.queue_run(
            conversation,
            contracts.RunBody(content="Use attachment", attachments=["attachment.txt"]),
            BackgroundTasks(),
            users[0],
            session,
        )
        stored = await session.scalar(
            select(Message).where(Message.conversation_id == conversation.id)
        )
        assert "Files available" in stored.content
        assert run.status == RunStatus.queued.value
        run.status = RunStatus.completed.value
        await session.commit()
        deleted = await conversations_api.delete_conversation(conversation.id, users[0], session)
        assert deleted is None
    async with database() as session:
        assert await session.get(Conversation, conversation.id) is None
