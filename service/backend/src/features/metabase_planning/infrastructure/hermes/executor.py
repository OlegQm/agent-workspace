"""Execute Metabase planning turns through persistent Hermes sessions."""

import asyncio
import json
import uuid

import httpx
from sqlalchemy import select, update

from features.agents.infrastructure.configuration.registry import get_agent
from features.chat.infrastructure.hermes.models import model_id_for_mode
from features.chat.infrastructure.hermes.runtime import (
    TEXT_DELTA_EVENTS,
    delete_hermes_session,
    hermes_event_kind,
    hermes_headers,
    mark_hermes_session_initialized,
    prepare_hermes_history,
    set_run_status,
    store_event,
    validate_hermes_session_id,
)
from features.metabase_planning.application.results import apply_planner_result
from features.metabase_planning.infrastructure.hermes.contracts import (
    PlannerResult,
    parse_planner_result,
)
from features.metabase_planning.infrastructure.persistence.models import MetabasePlanningState
from features.workspace.application.policies.operations import protected_paths
from features.workspace.infrastructure.confidentiality.guard import (
    RestrictedContentGuard,
    snapshot_workspace,
)
from infrastructure.database.models import (
    AgentRun,
    ConversationRuntime,
    Message,
    RunStatus,
    utcnow,
)
from infrastructure.database.session import SessionLocal

FILE_CONTEXT_NOTICE = """
[Workspace context boundary]
The listed files may be inspected with terminal and file tools inside the assigned workspace to
understand presentation, formulas, calculation approach, project structure, or user expectations.
Their values and claims are not authoritative chart data. Never use them to prove a metric or a
factual query result. Never include file content, paths, excerpts, secrets, links, or derivatives in
the structured plan or any review handoff. Do not modify files.
""".strip()
PLANNER_OUTPUT_REPAIR_REQUEST = """
[Planner JSON repair]
Your previous response did not match the required structured-output contract. Correct only its JSON
structure while preserving the same user-facing message, requirements, discovery decision, and
provenance. Do not call tools, perform discovery, add facts, or change the plan. In particular,
business_question must be one statement object, while the other plan sections named in the output
contract must be arrays of statement objects. Return exactly one corrected JSON object with no
Markdown fences or surrounding prose.
""".strip()
SAFE_PLANNER_OUTPUT_ERROR = (
    "The planner could not produce a valid requirements result after an automatic retry. "
    "Please send your message again."
)


class PlannerConfidentialityError(RuntimeError):
    """Signal that a planner turn exposed restricted workspace content."""


def planning_input(
    content: str,
    attachments: list[str],
    previous_signature: dict | None,
) -> str:
    """Build a planner turn with references but without reading attachment contents."""
    state_context = (
        "[Planning context]\n"
        f"previous_discovery_signature: {json.dumps(previous_signature, ensure_ascii=True)}"
    )
    if not attachments:
        return f"{content}\n\n{state_context}"
    references = "\n".join(f"- {path}" for path in attachments)
    return (
        f"{content}\n\n{state_context}\n\n{FILE_CONTEXT_NOTICE}\n\n"
        f"Workspace references:\n{references}"
    )


async def _complete_run(run_id: uuid.UUID) -> None:
    """Mark a planning run complete after structured state was committed."""
    async with SessionLocal() as session:
        run = await session.get(AgentRun, run_id)
        if run is None or run.finalized:
            return
        run.status = RunStatus.completed.value
        run.finalized = True
        run.updated_at = utcnow()
        await session.commit()
    await store_event(run_id, "run.completed", {"status": "completed"})


async def _execute_remote_turn(
    run_id: uuid.UUID,
    client: httpx.AsyncClient,
    agent,
    run: AgentRun,
    session_id: str,
    run_input: str,
    history: list[dict[str, str]],
    guard: RestrictedContentGuard,
) -> dict:
    """Execute one Hermes turn and return its completed remote status document."""
    payload = {
        "input": run_input,
        "session_id": session_id,
        "conversation_history": history,
        "instructions": f"{agent.instructions}\n\n{agent.metabase_planner_instructions}",
        "model": model_id_for_mode(agent.llm, run.model_mode),
        "provider": agent.llm.provider,
    }
    response = await client.post(
        f"{str(agent.hermes_url).rstrip('/')}/v1/runs",
        headers=hermes_headers(agent.id),
        json=payload,
    )
    response.raise_for_status()
    hermes_run_id = str(response.json()["run_id"])
    await set_run_status(run_id, RunStatus.running.value, hermes_run_id=hermes_run_id)
    await store_event(run_id, "run.started", {"hermes_run_id": hermes_run_id})

    event_name = "message"
    data_lines: list[str] = []
    async with client.stream(
        "GET",
        f"{str(agent.hermes_url).rstrip('/')}/v1/runs/{hermes_run_id}/events",
        headers=hermes_headers(agent.id),
    ) as stream:
        stream.raise_for_status()
        async for line in stream.aiter_lines():
            if line.startswith("event:"):
                event_name = line[6:].strip()
            elif line.startswith("data:"):
                data_lines.append(line[5:].strip())
            elif not line and data_lines:
                raw = "\n".join(data_lines)
                data_lines = []
                try:
                    event_payload = json.loads(raw)
                except json.JSONDecodeError:
                    event_payload = {"text": raw}
                kind = hermes_event_kind(event_name, event_payload)
                if kind in TEXT_DELTA_EVENTS:
                    continue
                await store_event(run_id, kind, guard.sanitize_payload(event_payload))
                if "approval" in kind and "response" not in kind:
                    await set_run_status(run_id, RunStatus.waiting_approval.value)

    status_response = await client.get(
        f"{str(agent.hermes_url).rstrip('/')}/v1/runs/{hermes_run_id}",
        headers=hermes_headers(agent.id),
    )
    status_response.raise_for_status()
    remote = status_response.json()
    if remote.get("status") != "completed" or not isinstance(remote.get("output"), str):
        raise RuntimeError("Hermes planning run did not return a completed structured result")
    return remote


def _sanitize_planner_output(
    guard: RestrictedContentGuard,
    before: dict,
    remote: dict,
) -> str:
    """Validate workspace effects and return a confidentiality-safe planner output."""
    blocked = guard.remove_generated_derivatives(before)
    sanitized, changed = guard.sanitize_text(
        remote["output"], tuple(item.relative_path for item in blocked)
    )
    if blocked or changed:
        raise PlannerConfidentialityError(
            "Planner output violated workspace confidentiality policy"
        )
    return sanitized


async def _parse_with_one_repair(
    run_id: uuid.UUID,
    client: httpx.AsyncClient,
    agent,
    run: AgentRun,
    session_id: str,
    guard: RestrictedContentGuard,
    before: dict,
    output: str,
) -> tuple[PlannerResult, dict | None]:
    """Parse a planner result and perform at most one schema-only repair turn."""
    try:
        return parse_planner_result(output), None
    except (TypeError, ValueError):
        pass

    try:
        history = await prepare_hermes_history(
            client,
            agent.id,
            session_id,
            initialized=True,
        )
        remote = await _execute_remote_turn(
            run_id,
            client,
            agent,
            run,
            session_id,
            PLANNER_OUTPUT_REPAIR_REQUEST,
            history,
            guard,
        )
        repaired_output = _sanitize_planner_output(guard, before, remote)
        return parse_planner_result(repaired_output), remote
    except PlannerConfidentialityError:
        raise
    except Exception as exc:
        raise RuntimeError(SAFE_PLANNER_OUTPUT_ERROR) from exc


async def execute_planning_run_with_client(
    run_id: uuid.UUID,
    client: httpx.AsyncClient,
) -> None:
    """Execute one planning run with a caller-owned HTTP client for testability."""
    guard: RestrictedContentGuard | None = None
    before = {}
    first_turn = False
    session_id: str | None = None
    agent_id: str | None = None
    try:
        async with SessionLocal() as session:
            claimed = await session.execute(
                update(AgentRun)
                .where(AgentRun.id == run_id, AgentRun.status == RunStatus.queued.value)
                .values(status=RunStatus.running.value, updated_at=utcnow())
            )
            await session.commit()
            if claimed.rowcount != 1:
                return
            run = await session.get(AgentRun, run_id)
            if run is None:
                return
            agent_id = run.agent_id
            agent = get_agent(agent_id)
            runtime = await session.get(ConversationRuntime, run.conversation_id)
            state = await session.get(MetabasePlanningState, run.conversation_id)
            latest = await session.scalar(
                select(Message)
                .where(Message.conversation_id == run.conversation_id)
                .order_by(Message.created_at.desc(), Message.id.desc())
                .limit(1)
            )
            if runtime is None or state is None or latest is None or latest.role != "user":
                raise RuntimeError("Planning runtime state is unavailable")
            session_id = validate_hermes_session_id(runtime.hermes_session_id)
            first_turn = runtime.initialized_at is None
            requirements_revision = state.requirements_revision
            guard = RestrictedContentGuard.build(
                agent.workspace_root,
                await protected_paths(session, agent.id),
            )
            before = snapshot_workspace(agent.workspace_root)
            run_input = planning_input(
                latest.content,
                list(latest.attachments or []),
                state.discovery_signature,
            )

        history = await prepare_hermes_history(
            client,
            agent.id,
            session_id,
            initialized=not first_turn,
        )
        remote = await _execute_remote_turn(
            run_id,
            client,
            agent,
            run,
            session_id,
            run_input,
            history,
            guard,
        )
        sanitized = _sanitize_planner_output(guard, before, remote)
        result, repaired_remote = await _parse_with_one_repair(
            run_id,
            client,
            agent,
            run,
            session_id,
            guard,
            before,
            sanitized,
        )
        if repaired_remote is not None:
            remote = repaired_remote
        async with SessionLocal() as session:
            await apply_planner_result(
                session,
                run.conversation_id,
                result,
                agent,
                expected_requirements_revision=requirements_revision,
            )
        await mark_hermes_session_initialized(run_id, remote)
        await _complete_run(run_id)
    except asyncio.CancelledError:
        if guard is not None:
            guard.remove_generated_derivatives(before)
        await set_run_status(run_id, RunStatus.cancelled.value)
        raise
    except Exception as exc:
        if first_turn and session_id and agent_id:
            await delete_hermes_session(agent_id, session_id)
        if guard is not None:
            guard.remove_generated_derivatives(before)
        await set_run_status(run_id, RunStatus.failed.value, error=str(exc))
        await store_event(run_id, "run.failed", {"error": str(exc)})


async def execute_planning_run(run_id: uuid.UUID) -> None:
    """Execute one planning turn with a hardened local Hermes transport."""
    timeout = httpx.Timeout(connect=15, read=None, write=60, pool=15)
    async with httpx.AsyncClient(
        timeout=timeout,
        trust_env=False,
        follow_redirects=False,
    ) as client:
        await execute_planning_run_with_client(run_id, client)
