"""Test the dedicated Hermes planning executor with local HTTP fakes."""

import asyncio
import json
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import select

from features.chat.infrastructure.hermes import runtime as hermes_runtime
from features.metabase_planning.infrastructure.hermes import executor
from features.metabase_planning.infrastructure.persistence.models import MetabasePlanningState
from infrastructure.database.models import (
    AgentRun,
    Conversation,
    ConversationRuntime,
    Message,
    RunEvent,
    User,
)
from tests.support.llm import configured_llm_profile


def _planner_output() -> str:
    """Return a valid collecting-state machine result."""
    return json.dumps(
        {
            "assistant_message": "Which reporting period should this cover?",
            "signature": {
                "business_intent": "Track revenue",
                "metric_definition": None,
                "source": None,
                "population_filter": None,
                "period_comparison": None,
                "granularity": None,
                "visualization": None,
            },
            "discovery": {"status": "no_match", "candidate": None},
            "plan": None,
        }
    )


def _complete_plan_output(*, business_question_as_list: bool = False) -> str:
    """Return a complete plan, optionally with the known malformed field shape."""
    statement = {"text": "How does monthly resource utilization change?", "provenance": "user_confirmed"}
    business_question: object = [statement] if business_question_as_list else statement
    return json.dumps(
        {
            "assistant_message": "The requirements plan is ready for review.",
            "signature": {
                "business_intent": "Understand monthly resource utilization",
                "metric_definition": "Resources in use and available",
                "source": "Configured operations database",
                "population_filter": "Resources within the selected scope",
                "period_comparison": "Current state",
                "granularity": "Resource",
                "visualization": "Stacked bar chart",
            },
            "discovery": {"status": "no_match", "candidate": None},
            "plan": {
                "business_question": business_question,
                "metrics": [statement],
                "sources": [statement],
                "period": [statement],
                "grain": [statement],
                "dimensions": [],
                "filters": [statement],
                "comparisons": [],
                "exclusions": [],
                "visualization": [statement],
                "expected_interpretation": [statement],
                "assumptions": [],
                "explicit_answers": [statement],
            },
        }
    )


@pytest.mark.integration
async def test_executor_uses_persistent_session_and_keeps_file_values_non_authoritative(
    database, users: tuple[User, User], tmp_path, monkeypatch
) -> None:
    """Pass safe file references to Hermes but never copy file content into its prompt."""
    workspace = tmp_path / "workspace"
    workspace.mkdir(exist_ok=True)
    workspace.joinpath("example.xlsx").write_text("SECRET FILE VALUE")
    async with database() as session:
        conversation = Conversation(
            user_id=users[0].id,
            agent_id="assistant",
            title="Revenue",
            kind="metabase_planning",
        )
        session.add(conversation)
        await session.flush()
        run = AgentRun(
            conversation_id=conversation.id,
            user_id=users[0].id,
            agent_id="assistant",
            model_mode="medium",
            status="queued",
        )
        session.add_all(
            [
                ConversationRuntime(
                    conversation_id=conversation.id,
                    hermes_session_id="open-agent-workspace_plan_test",
                ),
                MetabasePlanningState(conversation_id=conversation.id),
                Message(
                    conversation_id=conversation.id,
                    role="user",
                    content="Build a revenue chart",
                    attachments=["example.xlsx"],
                ),
                run,
            ]
        )
        await session.commit()
        run_id = run.id

    request_payloads: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        """Emulate a successful first Hermes planning turn."""
        if request.method == "DELETE":
            return httpx.Response(404)
        if request.url.path == "/api/sessions":
            return httpx.Response(200, json={"id": "open-agent-workspace_plan_test"})
        if request.method == "POST" and request.url.path == "/v1/runs":
            request_payloads.append(json.loads(request.content))
            return httpx.Response(200, json={"run_id": "remote-run"})
        if request.url.path.endswith("/events"):
            return httpx.Response(
                200,
                text='event: tool.completed\ndata: {"type":"tool.completed"}\n\n',
            )
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "session_id": "open-agent-workspace_plan_test",
                "output": _planner_output(),
            },
        )

    agent = SimpleNamespace(
        id="assistant",
        hermes_url="http://hermes.invalid",
        hermes_api_key="hidden",
        workspace_root=workspace,
        instructions="Assistant role instructions",
        metabase_planner_instructions="Planner instructions",
        resources=SimpleNamespace(metabase_collection_ids=[53]),
        llm=configured_llm_profile(),
    )
    monkeypatch.setattr(executor, "SessionLocal", database)
    monkeypatch.setattr(executor, "get_agent", lambda _: agent)
    monkeypatch.setattr(hermes_runtime, "get_agent", lambda _: agent)
    monkeypatch.setattr(executor, "hermes_headers", lambda _: {"Authorization": "Bearer hidden"})
    monkeypatch.setattr(executor, "protected_paths", lambda *_: _empty_paths())
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await executor.execute_planning_run_with_client(run_id, client)

    payload = request_payloads[0]
    assert payload["instructions"] == "Assistant role instructions\n\nPlanner instructions"
    assert "example.xlsx" in payload["input"]
    assert "requirements_revision" not in payload["input"]
    assert "SECRET FILE VALUE" not in payload["input"]
    assert payload["conversation_history"] == []
    async with database() as session:
        stored_run = await session.get(AgentRun, run_id)
        state = await session.get(MetabasePlanningState, conversation.id)
        assistant = await session.scalar(
            select(Message).where(
                Message.conversation_id == conversation.id,
                Message.role == "assistant",
            )
        )
        runtime = await session.get(ConversationRuntime, conversation.id)
        assert stored_run.status == "completed"
        assert stored_run.finalized is True
        assert state.discovery_status == "no_match"
        assert assistant.content.startswith("Which")
        assert runtime.initialized_at is not None


@pytest.mark.integration
async def test_executor_repairs_one_invalid_structured_result_in_the_same_session(
    database, users, tmp_path, monkeypatch
) -> None:
    """Retry once when Hermes returns valid JSON with an invalid planner schema."""
    run_id, conversation_id = await _persist_run(database, users[0])
    workspace = tmp_path / "workspace"
    workspace.mkdir(exist_ok=True)
    agent = _agent(workspace)
    posted_runs: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        """Return a malformed first result and a corrected repair result."""
        if request.method == "DELETE":
            return httpx.Response(404)
        if request.method == "POST" and request.url.path == "/api/sessions":
            return httpx.Response(200, json={"id": "created"})
        if request.method == "POST" and request.url.path == "/v1/runs":
            posted_runs.append(json.loads(request.content))
            return httpx.Response(200, json={"run_id": f"remote-{len(posted_runs)}"})
        if request.url.path.endswith("/events"):
            return httpx.Response(200, text="")
        if request.url.path.endswith("/messages"):
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"role": "user", "content": "Build a resource utilization chart"},
                        {"role": "assistant", "content": "Invalid structured result"},
                    ]
                },
            )
        if request.url.path.endswith("/remote-1"):
            return httpx.Response(
                200,
                json={"status": "completed", "output": _complete_plan_output(business_question_as_list=True)},
            )
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "session_id": None,
                "output": _complete_plan_output(),
            },
        )

    monkeypatch.setattr(executor, "SessionLocal", database)
    monkeypatch.setattr(executor, "get_agent", lambda _: agent)
    monkeypatch.setattr(hermes_runtime, "get_agent", lambda _: agent)
    monkeypatch.setattr(executor, "hermes_headers", lambda _: {})
    monkeypatch.setattr(executor, "protected_paths", lambda *_: _empty_paths())
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await executor.execute_planning_run_with_client(run_id, client)

    assert len(posted_runs) == 2
    assert posted_runs[1]["session_id"] == posted_runs[0]["session_id"]
    assert posted_runs[1]["conversation_history"]
    assert "Do not call tools" in posted_runs[1]["input"]
    assert "business_question" in posted_runs[1]["input"]
    async with database() as session:
        run = await session.get(AgentRun, run_id)
        state = await session.get(MetabasePlanningState, conversation_id)
    assert run.status == "completed"
    assert state.workflow_state == "plan_ready"
    assert state.structured_plan["business_question"]["text"].startswith("How")


@pytest.mark.integration
async def test_executor_exposes_safe_error_after_one_failed_repair(
    database, users, tmp_path, monkeypatch
) -> None:
    """Hide parser details and stop after one automatic repair attempt."""
    run_id, _ = await _persist_run(database, users[0])
    workspace = tmp_path / "workspace"
    workspace.mkdir(exist_ok=True)
    agent = _agent(workspace)
    post_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        """Return an invalid planner result for both allowed runs."""
        nonlocal post_count
        if request.method == "DELETE":
            return httpx.Response(404)
        if request.method == "POST" and request.url.path == "/api/sessions":
            return httpx.Response(200, json={"id": "created"})
        if request.method == "POST" and request.url.path == "/v1/runs":
            post_count += 1
            return httpx.Response(200, json={"run_id": f"remote-{post_count}"})
        if request.url.path.endswith("/events"):
            return httpx.Response(200, text="")
        if request.url.path.endswith("/messages"):
            return httpx.Response(200, json={"data": []})
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "session_id": None,
                "output": _complete_plan_output(business_question_as_list=True),
            },
        )

    async def delete(*_args) -> None:
        """Avoid external cleanup while exercising the safe failure path."""

    monkeypatch.setattr(executor, "SessionLocal", database)
    monkeypatch.setattr(executor, "get_agent", lambda _: agent)
    monkeypatch.setattr(hermes_runtime, "get_agent", lambda _: agent)
    monkeypatch.setattr(executor, "hermes_headers", lambda _: {})
    monkeypatch.setattr(executor, "protected_paths", lambda *_: _empty_paths())
    monkeypatch.setattr(executor, "delete_hermes_session", delete)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await executor.execute_planning_run_with_client(run_id, client)

    async with database() as session:
        run = await session.get(AgentRun, run_id)
        failure = await session.scalar(
            select(RunEvent).where(
                RunEvent.run_id == run_id,
                RunEvent.event_type == "run.failed",
            )
        )
    assert post_count == 2
    assert run.status == "failed"
    assert run.error == executor.SAFE_PLANNER_OUTPUT_ERROR
    assert failure.payload == {"error": executor.SAFE_PLANNER_OUTPUT_ERROR}
    assert "validation error" not in run.error.casefold()


@pytest.mark.unit
async def test_repair_preserves_confidentiality_failure(monkeypatch, tmp_path) -> None:
    """Never replace a restricted-output failure with the generic schema message."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    agent = _agent(workspace)

    async def history(*_args, **_kwargs) -> list[dict[str, str]]:
        """Return an initialized empty Hermes history."""
        return []

    async def remote(*_args, **_kwargs) -> dict:
        """Return a nominal completed repair turn."""
        return {"status": "completed", "output": _planner_output()}

    def reject(*_args, **_kwargs) -> str:
        """Represent restricted content found in the repaired output."""
        raise executor.PlannerConfidentialityError("confidentiality blocked")

    monkeypatch.setattr(executor, "prepare_hermes_history", history)
    monkeypatch.setattr(executor, "_execute_remote_turn", remote)
    monkeypatch.setattr(executor, "_sanitize_planner_output", reject)
    async with httpx.AsyncClient() as client:
        with pytest.raises(executor.PlannerConfidentialityError, match="confidentiality"):
            await executor._parse_with_one_repair(
                uuid.uuid4(),
                client,
                agent,
                SimpleNamespace(model_mode="medium"),
                "open-agent-workspace_plan_test",
                SimpleNamespace(),
                {},
                "invalid",
            )


async def _empty_paths() -> list[str]:
    """Return no restricted paths for the local executor test."""
    return []


def test_planning_input_without_attachments_contains_only_state_context() -> None:
    """Avoid adding a file boundary section when no workspace references exist."""
    value = executor.planning_input("Build revenue", [], {"source": "Stripe"})

    assert value.startswith("Build revenue\n\n[Planning context]")
    assert "Workspace references" not in value
    assert '"source": "Stripe"' in value


async def _persist_run(
    database,
    user: User,
    *,
    initialized: bool = False,
    include_state: bool = True,
) -> tuple[uuid.UUID, uuid.UUID]:
    """Persist one executable planning run and return run and conversation IDs."""
    async with database() as session:
        conversation = Conversation(
            user_id=user.id,
            agent_id="assistant",
            title="Revenue",
            kind="metabase_planning",
        )
        session.add(conversation)
        await session.flush()
        run = AgentRun(
            conversation_id=conversation.id,
            user_id=user.id,
            agent_id="assistant",
            model_mode="medium",
            status="queued",
        )
        records = [
            ConversationRuntime(
                conversation_id=conversation.id,
                hermes_session_id=f"open-agent-workspace_plan_{uuid.uuid4().hex}",
                initialized_at=datetime.now(UTC) if initialized else None,
            ),
            Message(
                conversation_id=conversation.id,
                role="user",
                content="Build a revenue chart",
                attachments=[],
            ),
            run,
        ]
        if include_state:
            records.append(MetabasePlanningState(conversation_id=conversation.id))
        session.add_all(records)
        await session.commit()
        return run.id, conversation.id


def _agent(workspace) -> SimpleNamespace:
    """Return one fully configured local planning agent."""
    return SimpleNamespace(
        id="assistant",
        hermes_url="http://hermes.invalid",
        hermes_api_key="hidden",
        workspace_root=workspace,
        instructions="Assistant role instructions",
        metabase_planner_instructions="Planner instructions",
        resources=SimpleNamespace(metabase_collection_ids=[53]),
        llm=configured_llm_profile(),
    )


@pytest.mark.integration
async def test_resumed_executor_handles_non_json_events_and_remote_failure(
    database, users, tmp_path, monkeypatch
) -> None:
    """Resume history, persist bounded events, and fail an incomplete structured run."""
    run_id, conversation_id = await _persist_run(database, users[0], initialized=True)
    workspace = tmp_path / "workspace"
    workspace.mkdir(exist_ok=True)
    agent = _agent(workspace)

    def handler(request: httpx.Request) -> httpx.Response:
        """Emulate a resumed Hermes run with mixed event payloads."""
        if request.url.path.endswith("/messages"):
            return httpx.Response(200, json={"data": [{"role": "user", "content": "Earlier"}]})
        if request.method == "POST" and request.url.path == "/v1/runs":
            payload = json.loads(request.content)
            assert payload["conversation_history"] == [{"role": "user", "content": "Earlier"}]
            return httpx.Response(200, json={"run_id": "remote-resumed"})
        if request.url.path.endswith("/events"):
            return httpx.Response(
                200,
                text=(
                    "event: message\ndata: not-json\n\n"
                    ": keep-alive\n"
                    'event: approval.requested\ndata: {"type":"approval.requested"}\n\n'
                    'event: message.delta\ndata: {"type":"message.delta","delta":"hidden"}\n\n'
                ),
            )
        return httpx.Response(200, json={"status": "failed", "output": None})

    monkeypatch.setattr(executor, "SessionLocal", database)
    monkeypatch.setattr(executor, "get_agent", lambda _: agent)
    monkeypatch.setattr(hermes_runtime, "get_agent", lambda _: agent)
    monkeypatch.setattr(executor, "hermes_headers", lambda _: {})
    monkeypatch.setattr(executor, "protected_paths", lambda *_: _empty_paths())
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await executor.execute_planning_run_with_client(run_id, client)

    async with database() as session:
        run = await session.get(AgentRun, run_id)
        events = list(
            await session.scalars(
                select(RunEvent).where(RunEvent.run_id == run_id).order_by(RunEvent.sequence)
            )
        )
    assert run.status == "failed"
    assert "completed structured result" in run.error
    assert any(event.event_type == "approval.requested" for event in events)
    assert all(event.event_type != "message.delta" for event in events)
    assert conversation_id == run.conversation_id


@pytest.mark.integration
async def test_executor_fails_missing_runtime_state_and_deletes_first_session(
    database, users, tmp_path, monkeypatch
) -> None:
    """Fail a malformed first turn and invoke best-effort session cleanup."""
    run_id, _ = await _persist_run(database, users[0], include_state=False)
    workspace = tmp_path / "workspace"
    workspace.mkdir(exist_ok=True)
    deleted: list[tuple[str, str]] = []

    async def delete(agent_id: str, session_id: str) -> None:
        """Record first-session cleanup."""
        deleted.append((agent_id, session_id))

    monkeypatch.setattr(executor, "SessionLocal", database)
    monkeypatch.setattr(executor, "get_agent", lambda _: _agent(workspace))
    monkeypatch.setattr(executor, "protected_paths", lambda *_: _empty_paths())
    monkeypatch.setattr(executor, "delete_hermes_session", delete)
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(500))) as client:
        await executor.execute_planning_run_with_client(run_id, client)

    async with database() as session:
        run = await session.get(AgentRun, run_id)
    assert run.status == "failed"
    assert "runtime state" in run.error
    assert deleted == []


@pytest.mark.integration
async def test_executor_rejects_stale_result_and_cleans_first_session(
    database, users, tmp_path, monkeypatch
) -> None:
    """Never apply a structured result for another requirements revision."""
    run_id, _ = await _persist_run(database, users[0])
    workspace = tmp_path / "workspace"
    workspace.mkdir(exist_ok=True)
    agent = _agent(workspace)
    deleted: list[tuple[str, str]] = []
    def handler(request: httpx.Request) -> httpx.Response:
        """Return a completed structured result."""
        if request.method == "DELETE":
            return httpx.Response(404)
        if request.url.path == "/api/sessions":
            return httpx.Response(200, json={"id": "created"})
        if request.method == "POST" and request.url.path == "/v1/runs":
            return httpx.Response(200, json={"run_id": "remote-stale"})
        if request.url.path.endswith("/events"):
            return httpx.Response(200, text="")
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "session_id": None,
                "output": _planner_output(),
            },
        )

    async def delete(agent_id: str, session_id: str) -> None:
        """Record first-session cleanup."""
        deleted.append((agent_id, session_id))

    async def reject_stale(*_args, expected_requirements_revision: int, **_kwargs) -> None:
        """Represent a revision changed while Hermes was producing its result."""
        assert expected_requirements_revision == 0
        raise ValueError("Planner result targeted a stale requirements revision")

    monkeypatch.setattr(executor, "SessionLocal", database)
    monkeypatch.setattr(executor, "get_agent", lambda _: agent)
    monkeypatch.setattr(hermes_runtime, "get_agent", lambda _: agent)
    monkeypatch.setattr(executor, "hermes_headers", lambda _: {})
    monkeypatch.setattr(executor, "protected_paths", lambda *_: _empty_paths())
    monkeypatch.setattr(executor, "delete_hermes_session", delete)
    monkeypatch.setattr(executor, "apply_planner_result", reject_stale)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await executor.execute_planning_run_with_client(run_id, client)

    async with database() as session:
        run = await session.get(AgentRun, run_id)
    assert run.status == "failed"
    assert "stale requirements" in run.error
    assert deleted and deleted[0][0] == "assistant"


@pytest.mark.integration
async def test_executor_cancellation_marks_run_and_reraises(
    database, users, tmp_path, monkeypatch
) -> None:
    """Preserve cancellation semantics and clean generated derivatives."""
    run_id, _ = await _persist_run(database, users[0])
    workspace = tmp_path / "workspace"
    workspace.mkdir(exist_ok=True)

    async def cancel(*_args, **_kwargs):
        """Cancel after local state and confidentiality snapshots exist."""
        raise asyncio.CancelledError

    monkeypatch.setattr(executor, "SessionLocal", database)
    monkeypatch.setattr(executor, "get_agent", lambda _: _agent(workspace))
    monkeypatch.setattr(executor, "protected_paths", lambda *_: _empty_paths())
    monkeypatch.setattr(executor, "prepare_hermes_history", cancel)
    async with httpx.AsyncClient() as client:
        with pytest.raises(asyncio.CancelledError):
            await executor.execute_planning_run_with_client(run_id, client)

    async with database() as session:
        run = await session.get(AgentRun, run_id)
    assert run.status == "cancelled"


@pytest.mark.integration
async def test_complete_run_ignores_missing_and_already_finalized_records(
    database, users, monkeypatch, tmp_path
) -> None:
    """Make completion idempotent when retries race with persistence changes."""
    monkeypatch.setattr(executor, "SessionLocal", database)
    await executor._complete_run(uuid.uuid4())
    run_id, _ = await _persist_run(database, users[0])
    async with database() as session:
        run = await session.get(AgentRun, run_id)
        run.finalized = True
        await session.commit()
    await executor._complete_run(run_id)

    async with database() as session:
        assert (await session.get(AgentRun, run_id)).status == "queued"


@pytest.mark.unit
async def test_executor_returns_if_claimed_run_disappears(monkeypatch) -> None:
    """Stop safely when a conversation deletion races with run startup."""
    class Claimed:
        """Represent a successful update result."""

        rowcount = 1

    class Session:
        """Return no run after a successful claim."""

        async def __aenter__(self):
            """Enter the fake persistence context."""
            return self

        async def __aexit__(self, *_args):
            """Exit the fake persistence context."""
            return

        async def execute(self, _statement):
            """Report a successfully claimed queued run."""
            return Claimed()

        async def commit(self):
            """Accept the claim transaction."""
            return

        async def get(self, _model, _identifier):
            """Represent a run deleted after it was claimed."""
            return

    monkeypatch.setattr(executor, "SessionLocal", Session)
    async with httpx.AsyncClient() as client:
        await executor.execute_planning_run_with_client(uuid.uuid4(), client)


@pytest.mark.unit
async def test_execute_planning_run_builds_hardened_client(monkeypatch) -> None:
    """Delegate the public background task through one caller-owned HTTP client."""
    calls: list[uuid.UUID] = []

    async def execute(run_id: uuid.UUID, client: httpx.AsyncClient) -> None:
        """Record delegation without issuing a request."""
        assert isinstance(client, httpx.AsyncClient)
        calls.append(run_id)

    run_id = uuid.uuid4()
    monkeypatch.setattr(executor, "execute_planning_run_with_client", execute)
    await executor.execute_planning_run(run_id)
    assert calls == [run_id]


@pytest.mark.integration
async def test_executor_ignores_a_run_that_is_no_longer_queued(database, users, monkeypatch) -> None:
    """Avoid a second Hermes turn when another worker already claimed the run."""
    run_id, _ = await _persist_run(database, users[0])
    async with database() as session:
        run = await session.get(AgentRun, run_id)
        run.status = "running"
        await session.commit()
    monkeypatch.setattr(executor, "SessionLocal", database)
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: pytest.fail("HTTP must not be called"))
    ) as client:
        await executor.execute_planning_run_with_client(run_id, client)


@pytest.mark.integration
async def test_executor_blocks_confidential_output_before_applying_planning_state(
    database, users, tmp_path, monkeypatch
) -> None:
    """Fail the turn when generated output reproduces a restricted workspace source."""
    run_id, _ = await _persist_run(database, users[0])
    workspace = tmp_path / "workspace"
    workspace.mkdir(exist_ok=True)
    agent = _agent(workspace)

    class Guard:
        """Report one generated restricted derivative."""

        def sanitize_payload(self, value):
            """Leave non-user-facing event metadata unchanged."""
            return value

        def remove_generated_derivatives(self, _before):
            """Return a bounded blocked-file descriptor."""
            return [SimpleNamespace(relative_path="blocked.xlsx")]

        def sanitize_text(self, value, _paths):
            """Leave output text unchanged for the derivative branch."""
            return value, False

    def handler(request: httpx.Request) -> httpx.Response:
        """Return a valid result accompanied by a blocked derivative."""
        if request.method == "DELETE":
            return httpx.Response(404)
        if request.url.path == "/api/sessions":
            return httpx.Response(200, json={"id": "created"})
        if request.method == "POST" and request.url.path == "/v1/runs":
            return httpx.Response(200, json={"run_id": "remote-blocked"})
        if request.url.path.endswith("/events"):
            return httpx.Response(200, text="")
        return httpx.Response(200, json={"status": "completed", "output": _planner_output()})

    monkeypatch.setattr(executor, "SessionLocal", database)
    monkeypatch.setattr(executor, "get_agent", lambda _: agent)
    monkeypatch.setattr(hermes_runtime, "get_agent", lambda _: agent)
    monkeypatch.setattr(executor, "hermes_headers", lambda _: {})
    monkeypatch.setattr(executor, "protected_paths", lambda *_: _empty_paths())
    monkeypatch.setattr(executor.RestrictedContentGuard, "build", lambda *_: Guard())
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await executor.execute_planning_run_with_client(run_id, client)

    async with database() as session:
        run = await session.get(AgentRun, run_id)
    assert run.status == "failed"
    assert "confidentiality policy" in run.error


@pytest.mark.unit
async def test_cancellation_before_guard_initialization_is_safe(monkeypatch) -> None:
    """Handle task cancellation even before workspace state has been loaded."""
    class Session:
        """Cancel while entering the initial persistence context."""

        async def __aenter__(self):
            """Cancel before a guard or run can be loaded."""
            raise asyncio.CancelledError

        async def __aexit__(self, *_args):
            """Exit the cancelled fake persistence context."""
            return

    async def status(*_args, **_kwargs):
        """Accept the best-effort cancelled status update."""

    monkeypatch.setattr(executor, "SessionLocal", Session)
    monkeypatch.setattr(executor, "set_run_status", status)
    with pytest.raises(asyncio.CancelledError):
        async with httpx.AsyncClient() as client:
            await executor.execute_planning_run_with_client(uuid.uuid4(), client)
