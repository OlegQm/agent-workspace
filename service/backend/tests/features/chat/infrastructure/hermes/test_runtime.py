"""Characterize Hermes transport, persistence, and recovery contracts."""

import asyncio
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
import respx
from sqlalchemy import select

from features.chat.infrastructure.hermes import runtime as hermes
from infrastructure.database.models import (
    AgentRun,
    Conversation,
    ConversationRuntime,
    Message,
    RunEvent,
    RunStatus,
    User,
    WorkspacePathPolicy,
)
from tests.support.llm import configured_llm_profile


@pytest.fixture
def runtime_agent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """Configure one isolated agent for all Hermes HTTP calls."""
    workspace = tmp_path / "assistant" / "workspace"
    workspace.mkdir(parents=True)
    configured = SimpleNamespace(
        id="assistant",
        hermes_url="http://hermes.test",
        hermes_api_key="runtime-key",
        workspace_root=workspace,
        instructions="Runtime instructions",
        llm=configured_llm_profile(),
    )
    monkeypatch.setattr(hermes, "get_agent", lambda _: configured)
    return configured


@pytest.fixture
async def persisted_run(database, runtime_agent) -> tuple[User, Conversation, AgentRun]:
    """Persist an initialized conversation and queued agent run."""
    async with database() as session:
        user = User(username="assistant", password_hash="unused", agent_id="assistant")
        session.add(user)
        await session.flush()
        conversation = Conversation(user_id=user.id, agent_id="assistant", title="Question")
        session.add(conversation)
        await session.flush()
        session.add(
            ConversationRuntime(
                conversation_id=conversation.id,
                hermes_session_id="session_1",
            )
        )
        session.add(Message(conversation_id=conversation.id, role="user", content="Question"))
        run = AgentRun(
            conversation_id=conversation.id,
            user_id=user.id,
            agent_id="assistant",
            status=RunStatus.queued.value,
        )
        session.add(run)
        await session.commit()
        await session.refresh(user)
        await session.refresh(conversation)
        await session.refresh(run)
    return user, conversation, run


def capabilities(*, compatible: bool = True) -> dict:
    """Return an exact standard Hermes capability document."""
    return {
        "features": {name: compatible for name in hermes.REQUIRED_HERMES_FEATURES},
        "endpoints": {name: {"path": f"/{name}"} for name in hermes.REQUIRED_HERMES_ENDPOINTS},
    }


class _SessionProxy:
    """Delegate an async session while permitting one controlled `get` race."""

    def __init__(self, session, index: int, get_override) -> None:
        """Store the real session and context-specific override."""
        self._session = session
        self._index = index
        self._get_override = get_override

    async def get(self, entity, *args, **kwargs):
        """Apply the configured race simulation before delegating to SQLAlchemy."""
        return await self._get_override(self._session, self._index, entity, *args, **kwargs)

    def __getattr__(self, name: str):
        """Delegate unmodified async-session APIs to the real session."""
        return getattr(self._session, name)


class _SessionContext:
    """Wrap a SQLAlchemy async-session context with a proxy object."""

    def __init__(self, session, index: int, get_override) -> None:
        """Keep the context parameters needed to construct the proxy."""
        self._session = session
        self._index = index
        self._get_override = get_override

    async def __aenter__(self):
        """Enter the real context and expose the proxy session."""
        await self._session.__aenter__()
        return _SessionProxy(self._session, self._index, self._get_override)

    async def __aexit__(self, exc_type, exc_value, traceback):
        """Close the real session context unchanged."""
        return await self._session.__aexit__(exc_type, exc_value, traceback)


class _SessionFactory:
    """Create indexed session contexts for deterministic run-race tests."""

    def __init__(self, session_factory, get_override) -> None:
        """Initialize the underlying factory and controlled override."""
        self._session_factory = session_factory
        self._get_override = get_override
        self._index = 0

    def __call__(self):
        """Return the next proxied async-session context."""
        self._index += 1
        return _SessionContext(
            self._session_factory(),
            self._index,
            self._get_override,
        )


async def _normal_get(session, _index: int, entity, *args, **kwargs):
    """Delegate a proxied `get` call without modifying its result."""
    return await session.get(entity, *args, **kwargs)


async def _add_queued_run(database, user: User, conversation: Conversation) -> AgentRun:
    """Add a fresh queued run to an existing persisted conversation."""
    async with database() as session:
        run = AgentRun(
            conversation_id=conversation.id,
            user_id=user.id,
            agent_id="assistant",
            status=RunStatus.queued.value,
        )
        session.add(run)
        await session.commit()
        await session.refresh(run)
    return run


@pytest.mark.unit
@respx.mock
async def test_capability_and_session_http_contract(runtime_agent) -> None:
    """Preserve standard capability checks and session create/delete requests."""
    endpoint = "http://hermes.test"
    respx.get(f"{endpoint}/v1/capabilities").mock(
        return_value=httpx.Response(200, json=capabilities())
    )
    await hermes.ensure_hermes_session_capability("assistant")
    assert hermes.hermes_headers("assistant") == {
        "Authorization": "Bearer runtime-key",
        "Content-Type": "application/json",
    }
    respx.delete(f"{endpoint}/api/sessions/session_1").mock(return_value=httpx.Response(404))
    respx.post(f"{endpoint}/api/sessions").mock(
        return_value=httpx.Response(201, json={"id": "session_1"})
    )
    async with httpx.AsyncClient() as client:
        await hermes.delete_hermes_session_with_client(client, "assistant", "session_1")
        await hermes.create_hermes_session(client, "assistant", "session_1")
    assert hermes.hermes_runtime_compatible({}) is False
    respx.get(f"{endpoint}/v1/capabilities").mock(
        return_value=httpx.Response(200, json=capabilities(compatible=False))
    )
    with pytest.raises(RuntimeError, match="required Hermes"):
        await hermes.ensure_hermes_session_capability("assistant")


@pytest.mark.integration
async def test_run_state_persistence_and_event_stream(database, persisted_run) -> None:
    """Preserve run event sequencing, result finalization, and SSE replay output."""
    _, conversation, run = persisted_run
    await hermes.store_event(run.id, "run.started", {"run": "hermes_1"})
    await hermes.set_run_status(run.id, RunStatus.running.value, hermes_run_id="hermes_1")
    await hermes.finalize_run(run.id, {"status": "completed", "output": "Answer"})
    async with database() as session:
        current = await session.get(AgentRun, run.id)
        messages = (
            await session.scalars(select(Message).where(Message.conversation_id == conversation.id))
        ).all()
        events = (await session.scalars(select(RunEvent).where(RunEvent.run_id == run.id))).all()
    assert current.status == RunStatus.completed.value
    assert current.finalized is True
    assert [message.role for message in messages] == ["user", "assistant"]
    assert [event.sequence for event in events] == [1, 2]
    rendered = [item async for item in hermes.event_stream(run.id)]
    assert "event: run-event" in rendered[0]
    assert "event: stream-end" in rendered[-1]


@pytest.mark.integration
async def test_mark_initialize_stop_and_approval_state(
    database, persisted_run, runtime_agent
) -> None:
    """Preserve state transitions around successful initialization, stop, and approval."""
    _, _, run = persisted_run
    await hermes.mark_hermes_session_initialized(run.id, {"status": "completed"})
    await hermes.mark_hermes_session_initialized(
        run.id, {"status": "completed", "session_id": "session_1"}
    )
    async with database() as session:
        stored = await session.get(AgentRun, run.id)
        stored.status = RunStatus.waiting_approval.value
        stored.hermes_run_id = "hermes_1"
        await session.commit()
        await session.refresh(stored)
    with respx.mock:
        respx.post("http://hermes.test/v1/runs/hermes_1/approval").mock(
            return_value=httpx.Response(200)
        )
        await hermes.approve_hermes_run(stored, "once")
    async with database() as session:
        approved = await session.get(AgentRun, run.id)
    assert approved.status == RunStatus.running.value
    with respx.mock:
        respx.post("http://hermes.test/v1/runs/hermes_1/stop").mock(
            return_value=httpx.Response(200)
        )
        await hermes.stop_hermes_run(approved)
    async with database() as session:
        stopped = await session.get(AgentRun, run.id)
    assert stopped.status == RunStatus.stopping.value


@pytest.mark.integration
@respx.mock
async def test_execute_run_uses_persistent_session_and_finalizes_output(
    database, persisted_run, runtime_agent, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Preserve first-turn session creation, run streaming, and successful finalization."""
    _, _, run = persisted_run
    respx.delete("http://hermes.test/api/sessions/session_1").mock(return_value=httpx.Response(404))
    respx.post("http://hermes.test/api/sessions").mock(
        return_value=httpx.Response(201, json={"id": "session_1"})
    )
    respx.post("http://hermes.test/v1/runs").mock(
        return_value=httpx.Response(201, json={"run_id": "hermes_1"})
    )
    respx.get("http://hermes.test/v1/runs/hermes_1/events").mock(
        return_value=httpx.Response(
            200, text='event: message.delta\ndata: {"type":"message.delta","delta":"Answer"}\n\n'
        )
    )
    respx.get("http://hermes.test/v1/runs/hermes_1").mock(
        return_value=httpx.Response(
            200, json={"status": "completed", "output": "Answer", "session_id": "session_1"}
        )
    )
    await hermes.execute_run(run.id)
    async with database() as session:
        result = await session.get(AgentRun, run.id)
        runtime = await session.get(ConversationRuntime, run.conversation_id)
        messages = (
            await session.scalars(
                select(Message).where(Message.conversation_id == run.conversation_id)
            )
        ).all()
    assert result.status == RunStatus.completed.value
    assert runtime.initialized_at is not None
    assert messages[-1].content == "Answer"


@pytest.mark.integration
@respx.mock
async def test_recovery_missing_or_terminal_run_contract(
    database, persisted_run, runtime_agent
) -> None:
    """Preserve restart recovery failures and terminal Hermes result finalization."""
    _, _, run = persisted_run
    await hermes.recover_run(run.id)
    async with database() as session:
        failed = await session.get(AgentRun, run.id)
        failed.hermes_run_id = "hermes_1"
        failed.status = RunStatus.running.value
        await session.commit()
    respx.get("http://hermes.test/v1/runs/hermes_1").mock(
        return_value=httpx.Response(200, json={"status": "cancelled", "session_id": "session_1"})
    )
    await hermes.recover_run(run.id)
    async with database() as session:
        recovered = await session.get(AgentRun, run.id)
    assert recovered.status == RunStatus.cancelled.value


@pytest.mark.integration
@respx.mock
async def test_hermes_failure_and_guard_branches(
    database, persisted_run, runtime_agent, monkeypatch
) -> None:
    """Preserve explicit runtime errors, malformed histories, and failed-run persistence."""
    _, _, run = persisted_run
    respx.get("http://hermes.test/v1/capabilities").mock(return_value=httpx.Response(503))
    with pytest.raises(RuntimeError, match="unavailable"):
        await hermes.ensure_hermes_session_capability("assistant")
    assert (
        hermes.normalize_hermes_history(
            [None, {"role": "system", "content": "x"}, {"role": "unknown", "content": "x"}]
        )
        == []
    )
    with pytest.raises(TypeError):
        hermes.normalize_hermes_history({})
    respx.get("http://hermes.test/api/sessions/session_1/messages").mock(
        return_value=httpx.Response(200, json={"data": {}})
    )
    async with httpx.AsyncClient() as client:
        with pytest.raises(TypeError):
            await hermes.fetch_hermes_history(client, "assistant", "session_1")
    await hermes.set_run_status(__import__("uuid").uuid4(), "failed")
    await hermes.finalize_run(run.id, {"status": "unknown", "error": "failure"})
    async with database() as session:
        failed = await session.get(AgentRun, run.id)
    assert failed.status == RunStatus.failed.value
    uninitialized = AgentRun(
        id=__import__("uuid").uuid4(),
        conversation_id=run.conversation_id,
        user_id=run.user_id,
        agent_id="assistant",
    )
    with pytest.raises(RuntimeError, match="not initialized"):
        await hermes.approve_hermes_run(uninitialized, "once")


@pytest.mark.integration
@respx.mock
async def test_session_history_and_initialization_error_contracts(
    database, persisted_run, runtime_agent, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Preserve missing-session, pagination, and initialization consistency failures."""
    _, conversation, run = persisted_run
    endpoint = "http://hermes.test"
    assert hermes.hermes_runtime_compatible([]) is False
    with pytest.raises(RuntimeError, match="Invalid Hermes"):
        hermes.validate_hermes_session_id("spaces are invalid")
    respx.get(f"{endpoint}/api/sessions/session_1/messages").mock(return_value=httpx.Response(404))
    async with httpx.AsyncClient() as client:
        with pytest.raises(RuntimeError, match="persistent Hermes session is missing"):
            await hermes.fetch_hermes_history(client, "assistant", "session_1")

    page = [{"role": "user", "content": "first"}] * 500
    route = respx.get(f"{endpoint}/api/sessions/session_1/messages")
    route.side_effect = [
        httpx.Response(200, json={"data": page}),
        httpx.Response(
            200, json={"data": [{"role": "tool", "tool_name": "files", "content": "done"}]}
        ),
        httpx.Response(200, json={"data": page}),
        httpx.Response(
            200, json={"data": [{"role": "tool", "tool_name": "files", "content": "done"}]}
        ),
    ]
    async with httpx.AsyncClient() as client:
        history = await hermes.fetch_hermes_history(client, "assistant", "session_1")
        assert history[-1] == {"role": "assistant", "content": "[Tool result from files]\ndone"}
        assert (
            await hermes.prepare_hermes_history(client, "assistant", "session_1", initialized=True)
            == history
        )

    route.side_effect = [httpx.Response(200, json={"data": page}) for _ in range(21)]
    async with httpx.AsyncClient() as client:
        with pytest.raises(RuntimeError, match="safety limit"):
            await hermes.fetch_hermes_history(client, "assistant", "session_1")

    async with database() as session:
        stored = await session.get(AgentRun, run.id)
        stored.status = RunStatus.completed.value
        await session.delete(await session.get(ConversationRuntime, conversation.id))
        await session.commit()
    with pytest.raises(RuntimeError, match="no persistent Hermes session"):
        await hermes.mark_hermes_session_initialized(run.id, {"status": "completed"})
    assert await hermes.mark_hermes_session_initialized(run.id, {"status": "failed"}) is None


@pytest.mark.integration
@respx.mock
async def test_hermes_lifecycle_noop_and_recovery_branches(
    database, persisted_run, runtime_agent, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Preserve no-op transitions, remote failures, and intermediate recovery polling."""
    _, _, run = persisted_run
    endpoint = "http://hermes.test"
    await hermes.stop_hermes_run(SimpleNamespace(id=__import__("uuid").uuid4(), agent_id="assistant"))
    async with database() as session:
        stored = await session.get(AgentRun, run.id)
        stored.status = RunStatus.running.value
        stored.hermes_run_id = None
        await session.commit()
    await hermes.stop_hermes_run(run)
    async with database() as session:
        assert (await session.get(AgentRun, run.id)).status == RunStatus.cancelled.value
        stored = await session.get(AgentRun, run.id)
        stored.status = RunStatus.running.value
        stored.hermes_run_id = "hermes_1"
        await session.commit()

    respx.post(f"{endpoint}/v1/runs/hermes_1/stop").mock(return_value=httpx.Response(500))
    with pytest.raises(httpx.HTTPStatusError):
        await hermes.stop_hermes_run(run)
    respx.delete(f"{endpoint}/api/sessions/session_1").mock(return_value=httpx.Response(500))
    await hermes.delete_hermes_session("assistant", "session_1")

    statuses = [
        httpx.Response(200, json={"status": "waiting_approval"}),
        httpx.Response(200, json={"status": "completed", "session_id": "session_1"}),
    ]
    respx.get(f"{endpoint}/v1/runs/hermes_1").side_effect = statuses
    monkeypatch.setattr(hermes.asyncio, "sleep", lambda _: _async_noop())
    await hermes.recover_run(run.id)
    async with database() as session:
        assert (await session.get(AgentRun, run.id)).status == RunStatus.completed.value


async def _async_noop() -> None:
    """Provide a completed awaitable for poll-loop tests."""


@pytest.mark.integration
@respx.mock
async def test_execute_run_event_and_failure_paths(
    database, persisted_run, runtime_agent, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Preserve event parsing, runtime stop, and first-turn failure cleanup behavior."""
    _, _, run = persisted_run
    endpoint = "http://hermes.test"
    respx.delete(f"{endpoint}/api/sessions/session_1").mock(return_value=httpx.Response(404))
    respx.post(f"{endpoint}/api/sessions").mock(return_value=httpx.Response(201))
    respx.post(f"{endpoint}/v1/runs").mock(
        return_value=httpx.Response(201, json={"run_id": "hermes_1"})
    )
    respx.get(f"{endpoint}/v1/runs/hermes_1/events").mock(
        return_value=httpx.Response(
            200,
            text=(
                "event: approval.request\ndata: {invalid json}\n\n"
                'event: run.completed\ndata: {"type":"run.completed"}\n\n'
            ),
        )
    )
    respx.get(f"{endpoint}/v1/runs/hermes_1").mock(
        return_value=httpx.Response(200, json={"status": "completed", "session_id": "session_1"})
    )
    await hermes.execute_run(run.id)
    async with database() as session:
        events = (await session.scalars(select(RunEvent).where(RunEvent.run_id == run.id))).all()
        assert any(event.event_type == "approval.request" for event in events)

    async with database() as session:
        failed = AgentRun(
            conversation_id=run.conversation_id,
            user_id=run.user_id,
            agent_id="assistant",
            status=RunStatus.queued.value,
        )
        session.add(failed)
        await session.commit()
        await session.refresh(failed)
    respx.post(f"{endpoint}/v1/runs").mock(return_value=httpx.Response(500))
    await hermes.execute_run(failed.id)
    async with database() as session:
        assert (await session.get(AgentRun, failed.id)).status == RunStatus.failed.value


@pytest.mark.integration
async def test_finalize_and_recovery_scheduler_edge_contracts(
    database, persisted_run, monkeypatch
) -> None:
    """Preserve duplicate finalization, absent-run handling, and scheduled recovery registration."""
    _, _, run = persisted_run
    await hermes.finalize_run(run.id, {"status": "completed"})
    await hermes.finalize_run(run.id, {"status": "completed", "output": "ignored"})
    await hermes.finalize_run(__import__("uuid").uuid4(), {"status": "completed"})
    scheduled: list[object] = []

    async def recover(_: object) -> None:
        """Complete immediately when the startup scheduler invokes recovery."""

    original_create_task = hermes.asyncio.create_task

    def create_task(coroutine):
        """Capture the task and use the normal event-loop task constructor."""
        scheduled.append(coroutine)
        return original_create_task(coroutine)

    monkeypatch.setattr(hermes, "recover_run", recover)
    monkeypatch.setattr(hermes.asyncio, "create_task", create_task)
    async with database() as session:
        active = await session.get(AgentRun, run.id)
        active.status = RunStatus.running.value
        await session.commit()
    await hermes.recover_interrupted_runs()
    await __import__("asyncio").sleep(0)
    assert scheduled


@pytest.mark.integration
async def test_hermes_remaining_persistence_and_early_execution_failures(
    database, persisted_run, runtime_agent
) -> None:
    """Preserve fail-closed behavior for missing runtime state and invalid session finalization."""
    user, _, run = persisted_run
    with pytest.raises(RuntimeError, match="Run disappeared"):
        await hermes.mark_hermes_session_initialized(
            __import__("uuid").uuid4(), {"status": "completed"}
        )
    with pytest.raises(RuntimeError, match="different session"):
        await hermes.mark_hermes_session_initialized(
            run.id, {"status": "completed", "session_id": "other_session"}
        )
    assert hermes.normalize_hermes_history([{"role": "user", "content": 1}]) == []

    async with database() as session:
        completed = await session.get(AgentRun, run.id)
        completed.status = RunStatus.completed.value
        await session.commit()
    await hermes.execute_run(run.id)

    async with database() as session:
        no_runtime_conversation = Conversation(
            user_id=user.id, agent_id="assistant", title="No runtime"
        )
        session.add(no_runtime_conversation)
        await session.flush()
        no_runtime = AgentRun(
            conversation_id=no_runtime_conversation.id,
            user_id=user.id,
            agent_id="assistant",
            status=RunStatus.queued.value,
        )
        session.add(no_runtime)
        await session.commit()
        await session.refresh(no_runtime)
    await hermes.execute_run(no_runtime.id)

    async with database() as session:
        no_message_conversation = Conversation(
            user_id=user.id, agent_id="assistant", title="No message"
        )
        session.add(no_message_conversation)
        await session.flush()
        session.add(
            ConversationRuntime(
                conversation_id=no_message_conversation.id, hermes_session_id="session_no_message"
            )
        )
        no_message = AgentRun(
            conversation_id=no_message_conversation.id,
            user_id=user.id,
            agent_id="assistant",
            status=RunStatus.queued.value,
        )
        session.add(no_message)
        await session.commit()
        await session.refresh(no_message)
    await hermes.execute_run(no_message.id)

    async with database() as session:
        no_id_conversation = Conversation(
            user_id=user.id, agent_id="assistant", title="No session id"
        )
        session.add(no_id_conversation)
        await session.flush()
        session.add(
            ConversationRuntime(conversation_id=no_id_conversation.id, hermes_session_id=None)
        )
        session.add(Message(conversation_id=no_id_conversation.id, role="user", content="Question"))
        no_id = AgentRun(
            conversation_id=no_id_conversation.id,
            user_id=user.id,
            agent_id="assistant",
            status=RunStatus.queued.value,
        )
        session.add(no_id)
        await session.commit()
        await session.refresh(no_id)
    await hermes.execute_run(no_id.id)
    async with database() as session:
        assert (await session.get(AgentRun, no_runtime.id)).status == RunStatus.failed.value
        assert (await session.get(AgentRun, no_message.id)).status == RunStatus.failed.value
        assert (await session.get(AgentRun, no_id.id)).status == RunStatus.failed.value


@pytest.mark.integration
@respx.mock
async def test_hermes_recovery_failure_event_contract(
    database, persisted_run, runtime_agent
) -> None:
    """Preserve failed recovery status and event persistence when Hermes polling fails."""
    _, _, run = persisted_run
    async with database() as session:
        stored = await session.get(AgentRun, run.id)
        stored.hermes_run_id = "hermes_failure"
        stored.status = RunStatus.running.value
        await session.commit()
    respx.get("http://hermes.test/v1/runs/hermes_failure").mock(return_value=httpx.Response(500))
    await hermes.recover_run(run.id)
    async with database() as session:
        failed = await session.get(AgentRun, run.id)
        events = (await session.scalars(select(RunEvent).where(RunEvent.run_id == run.id))).all()
    assert failed.status == RunStatus.failed.value
    assert events[-1].event_type == "run.failed"


@pytest.mark.integration
@respx.mock
async def test_execute_run_observes_concurrent_state_boundaries(
    database, persisted_run, runtime_agent, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Preserve explicit handling of claim, deletion, stop, and pre-submit races."""
    user, conversation, run = persisted_run

    async def missing_claimed_run(_session, index: int, entity, *args, **kwargs):
        """Remove the claimed run before its first read in the execution transaction."""
        if index == 1 and entity is AgentRun:
            return None
        return await _normal_get(_session, index, entity, *args, **kwargs)

    monkeypatch.setattr(
        hermes,
        "SessionLocal",
        _SessionFactory(database, missing_claimed_run),
    )
    await hermes.execute_run(run.id)
    async with database() as session:
        current = await session.get(AgentRun, run.id)
        current.status = RunStatus.failed.value
        await session.commit()

    pre_submit = await _add_queued_run(database, user, conversation)

    async def stop_before_submission(*_args, **_kwargs):
        """Change the run state after history preparation and before submission."""
        async with database() as session:
            current = await session.get(AgentRun, pre_submit.id)
            current.status = RunStatus.stopping.value
            await session.commit()
        return []

    monkeypatch.setattr(hermes, "SessionLocal", database)
    monkeypatch.setattr(hermes, "prepare_hermes_history", stop_before_submission)
    await hermes.execute_run(pre_submit.id)
    async with database() as session:
        current = await session.get(AgentRun, pre_submit.id)
        current.status = RunStatus.failed.value
        await session.commit()

    deleted_after_submit = await _add_queued_run(database, user, conversation)

    async def no_history(*_args, **_kwargs):
        """Avoid HTTP session setup while exercising the post-submit read race."""
        return []

    async def missing_current(session, index: int, entity, *args, **kwargs):
        """Simulate deletion between Hermes acceptance and local persistence."""
        if index == 3 and entity is AgentRun:
            return None
        return await _normal_get(session, index, entity, *args, **kwargs)

    monkeypatch.setattr(hermes, "prepare_hermes_history", no_history)
    monkeypatch.setattr(
        hermes,
        "SessionLocal",
        _SessionFactory(database, missing_current),
    )
    respx.post("http://hermes.test/v1/runs").mock(
        return_value=httpx.Response(201, json={"run_id": "hermes_deleted"})
    )
    await hermes.execute_run(deleted_after_submit.id)
    async with database() as session:
        current = await session.get(AgentRun, deleted_after_submit.id)
        current.status = RunStatus.failed.value
        await session.commit()

    stopped_after_submit = await _add_queued_run(database, user, conversation)

    async def stopping_current(session, index: int, entity, *args, **kwargs):
        """Expose a stopping state when the accepted Hermes run is persisted."""
        current = await _normal_get(session, index, entity, *args, **kwargs)
        if index == 3 and entity is AgentRun:
            current.status = RunStatus.stopping.value
        return current

    monkeypatch.setattr(
        hermes,
        "SessionLocal",
        _SessionFactory(database, stopping_current),
    )
    respx.post("http://hermes.test/v1/runs").mock(
        return_value=httpx.Response(201, json={"run_id": "hermes_stopping"})
    )
    stop = respx.post("http://hermes.test/v1/runs/hermes_stopping/stop").mock(
        return_value=httpx.Response(200)
    )
    await hermes.execute_run(stopped_after_submit.id)
    assert stop.called


@pytest.mark.integration
async def test_execute_run_cancellation_and_keepalive_contract(
    database, persisted_run, runtime_agent, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Preserve cancellation cleanup and the idle SSE keep-alive protocol."""
    _, _, run = persisted_run
    entered = asyncio.Event()
    release = asyncio.Event()

    async def block_history(*_args, **_kwargs):
        """Pause a run after its guard and workspace snapshot have been created."""
        entered.set()
        await release.wait()
        return []

    monkeypatch.setattr(hermes, "prepare_hermes_history", block_history)
    task = asyncio.create_task(hermes.execute_run(run.id))
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    async with database() as session:
        assert (await session.get(AgentRun, run.id)).status == RunStatus.cancelled.value

    async with database() as session:
        current = await session.get(AgentRun, run.id)
        current.status = RunStatus.running.value
        await session.commit()
    monkeypatch.setattr(hermes.asyncio, "sleep", lambda _: _async_noop())
    stream = hermes.event_stream(run.id)
    assert await anext(stream) == ": keep-alive\n\n"
    assert await anext(stream) == ": keep-alive\n\n"
    await stream.aclose()


@pytest.mark.integration
@respx.mock
async def test_execute_run_restricted_output_and_failure_cleanup_contract(
    database, persisted_run, runtime_agent, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Preserve redaction of protected output and derivative cleanup after failures."""
    _, conversation, run = persisted_run
    source = runtime_agent.workspace_root / "restricted.txt"
    source.write_text("restricted " * 40)
    async with database() as session:
        session.add(WorkspacePathPolicy(agent_id="assistant", path="restricted.txt"))
        await session.commit()

    endpoint = "http://hermes.test"
    respx.delete(f"{endpoint}/api/sessions/session_1").mock(return_value=httpx.Response(404))
    respx.post(f"{endpoint}/api/sessions").mock(return_value=httpx.Response(201))
    respx.post(f"{endpoint}/v1/runs").mock(
        return_value=httpx.Response(201, json={"run_id": "hermes_restricted"})
    )
    respx.get(f"{endpoint}/v1/runs/hermes_restricted/events").mock(
        return_value=httpx.Response(
            200,
            text=('\nevent: message.delta\ndata: {"type":"message.delta","delta":"blocked"}\n\n'),
        )
    )
    respx.get(f"{endpoint}/v1/runs/hermes_restricted").mock(
        return_value=httpx.Response(
            200,
            json={"status": "completed", "output": source.read_text(), "session_id": "session_1"},
        )
    )
    await hermes.execute_run(run.id)
    async with database() as session:
        events = (await session.scalars(select(RunEvent).where(RunEvent.run_id == run.id))).all()
        messages = (
            await session.scalars(select(Message).where(Message.conversation_id == conversation.id))
        ).all()
    assert not any(event.event_type == "message.delta" for event in events)
    assert any(event.event_type == "security.restricted_output_blocked" for event in events)
    assert "cannot create, copy, convert" in messages[-1].content

    failing = await _add_queued_run(database, (await _run_user(database, run.id)), conversation)
    async with database() as session:
        runtime = await session.get(ConversationRuntime, conversation.id)
        runtime.initialized_at = None
        session.add(Message(conversation_id=conversation.id, role="user", content="Follow up"))
        await session.commit()

    async def create_then_fail(*_args, **_kwargs):
        """Create a prohibited derivative before simulating an upstream run failure."""
        (runtime_agent.workspace_root / "copy.txt").write_text(source.read_text())
        raise RuntimeError("run failed after generating restricted content")

    monkeypatch.setattr(hermes, "prepare_hermes_history", create_then_fail)
    await hermes.execute_run(failing.id)
    async with database() as session:
        failed_events = (
            await session.scalars(select(RunEvent).where(RunEvent.run_id == failing.id))
        ).all()
        failed = await session.get(AgentRun, failing.id)
    assert failed.status == RunStatus.failed.value
    assert any(event.event_type == "security.restricted_output_blocked" for event in failed_events)
    assert not (runtime_agent.workspace_root / "copy.txt").exists()


async def _run_user(database, run_id) -> User:
    """Load the persisted run owner for a follow-up run in the same conversation."""
    async with database() as session:
        run = await session.get(AgentRun, run_id)
        return await session.get(User, run.user_id)


@pytest.mark.integration
async def test_finalize_and_cancellation_tolerate_disappearing_local_state(
    database, persisted_run, runtime_agent, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Preserve finalization and cancellation when local state disappears mid-turn."""
    _, _, run = persisted_run

    async def missing_conversation(session, index: int, entity, *args, **kwargs):
        """Hide the conversation only from the finalize transaction."""
        if index == 1 and entity is Conversation:
            return None
        return await _normal_get(session, index, entity, *args, **kwargs)

    monkeypatch.setattr(
        hermes,
        "SessionLocal",
        _SessionFactory(database, missing_conversation),
    )
    await hermes.finalize_run(run.id, {"status": "completed"})

    calls = 0

    class CancelledContext:
        """Raise cancellation before `execute_run` can construct a confidentiality guard."""

        async def __aenter__(self):
            """Raise the cancellation that the orchestrator must preserve."""
            raise asyncio.CancelledError

        async def __aexit__(self, exc_type, exc_value, traceback):
            """Satisfy the async context-manager protocol."""
            return False

    def cancel_once():
        """Return one cancelled context, then real persistence for cleanup."""
        nonlocal calls
        calls += 1
        return CancelledContext() if calls == 1 else database()

    monkeypatch.setattr(hermes, "SessionLocal", cancel_once)
    with pytest.raises(asyncio.CancelledError):
        await hermes.execute_run(run.id)
