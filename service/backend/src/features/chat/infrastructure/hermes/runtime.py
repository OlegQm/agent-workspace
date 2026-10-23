"""Orchestrate persistent native Hermes sessions and agent runs."""

import asyncio
import json
import logging
import re
import uuid
from collections.abc import AsyncIterator

import httpx
from sqlalchemy import func, select, update

from features.agents.infrastructure.configuration.registry import get_agent
from features.chat.infrastructure.hermes.models import model_id_for_mode
from features.workspace.application.policies.operations import protected_paths
from features.workspace.infrastructure.confidentiality.guard import (
    RestrictedContentGuard,
    snapshot_workspace,
)
from infrastructure.database.models import (
    ACTIVE_RUN_STATUSES,
    AgentRun,
    Conversation,
    ConversationRuntime,
    Message,
    RunEvent,
    RunStatus,
    utcnow,
)
from infrastructure.database.session import SessionLocal

TERMINAL_STATUSES = {
    RunStatus.completed.value,
    RunStatus.failed.value,
    RunStatus.cancelled.value,
}
RECOVERY_TASKS: set[asyncio.Task] = set()
HERMES_SESSION_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
logger = logging.getLogger(__name__)
TEXT_DELTA_EVENTS = {"message.delta", "assistant.delta", "content.delta", "text.delta"}
RESTRICTED_TURN_REMINDER = """

[Mandatory confidentiality policy]
The workspace contains restricted analysis-only files listed in
../workspace-access-policy.json. Before any file operation, read that policy. If this request asks
to copy, duplicate, rename-and-copy, convert, export, archive, encode, download, or provide a link
to a restricted file or derivative, refuse immediately without calling a tool or running a command.
Never claim that a blocked copy exists and never construct a download URL for it, including in a
follow-up turn. Restricted files may be used only for a limited aggregate, conclusion, or a specific
analytical answer, with no more than a 25-word excerpt.
A file is restricted only when its normalized relative path exactly matches a protected path or is
inside a protected directory. Do not transfer protection to files with similar names, other report
months, or the same template. Unprotected files may be copied and downloaded normally.
""".strip()


def hermes_event_kind(event_name: str, payload: dict) -> str:
    """Handle hermes event kind."""
    return str(payload.get("type") or payload.get("event") or event_name)


def hermes_headers(agent_id: str) -> dict[str, str]:
    """Handle hermes headers."""
    agent = get_agent(agent_id)
    return {
        "Authorization": f"Bearer {agent.hermes_api_key}",
        "Content-Type": "application/json",
    }


REQUIRED_HERMES_FEATURES = {
    "run_submission",
    "run_status",
    "run_events_sse",
    "run_stop",
    "run_approval_response",
    "approval_events",
    "session_resources",
}
REQUIRED_HERMES_ENDPOINTS = {
    "runs",
    "run_status",
    "run_events",
    "run_approval",
    "run_stop",
    "session_create",
    "session_delete",
    "session_messages",
}


class HermesClient:
    """Call the standard Hermes API for one configured agent runtime."""

    def __init__(self, client: httpx.AsyncClient, agent_id: str) -> None:
        """Bind a caller-owned HTTP client to one agent runtime."""
        self.client = client
        self.agent = get_agent(agent_id)
        self.base_url = str(self.agent.hermes_url).rstrip("/")

    @property
    def headers(self) -> dict[str, str]:
        """Return authorization headers for this agent runtime."""
        return hermes_headers(self.agent.id)

    async def capabilities(self) -> object:
        """Fetch and validate the runtime capability response."""
        response = await self.client.get(
            f"{self.base_url}/v1/capabilities",
            headers=self.headers,
        )
        response.raise_for_status()
        return response.json()

    async def delete_session(self, session_id: str) -> None:
        """Delete one persistent session when it exists."""
        validate_hermes_session_id(session_id)
        response = await self.client.delete(
            f"{self.base_url}/api/sessions/{session_id}",
            headers=self.headers,
        )
        if response.status_code != 404:
            response.raise_for_status()

    async def create_session(self, session_id: str) -> None:
        """Create an empty persistent session."""
        validate_hermes_session_id(session_id)
        response = await self.client.post(
            f"{self.base_url}/api/sessions",
            headers=self.headers,
            json={"id": session_id, "source": "api_server"},
        )
        response.raise_for_status()

    async def fetch_history(self, session_id: str) -> list[dict[str, str]]:
        """Fetch and normalize every persisted message for a session."""
        validate_hermes_session_id(session_id)
        messages: list[dict] = []
        offset = 0
        while True:
            response = await self.client.get(
                f"{self.base_url}/api/sessions/{session_id}/messages",
                headers=self.headers,
                params={"limit": 500, "offset": offset, "order": "oldest"},
            )
            if response.status_code == 404:
                raise RuntimeError(
                    "The persistent Hermes session is missing. Create a new conversation or restore "
                    "the agent state from a matching backup."
                )
            response.raise_for_status()
            payload = response.json()
            page = payload.get("data") if isinstance(payload, dict) else payload
            if not isinstance(page, list):
                raise TypeError("Hermes returned invalid session history")
            messages.extend(item for item in page if isinstance(item, dict))
            if len(messages) > 10_000:
                raise RuntimeError("Hermes session history exceeds the supported safety limit")
            if len(page) < 500:
                break
            offset += len(page)
        return normalize_hermes_history(messages)

    async def stop_run(self, run_id: str) -> None:
        """Request cancellation of an initialized Hermes run."""
        response = await self.client.post(
            f"{self.base_url}/v1/runs/{run_id}/stop",
            headers=self.headers,
        )
        response.raise_for_status()

    async def approve_run(self, run_id: str, decision: str) -> None:
        """Submit one approval decision to an initialized Hermes run."""
        response = await self.client.post(
            f"{self.base_url}/v1/runs/{run_id}/approval",
            headers=self.headers,
            json={"choice": decision},
        )
        response.raise_for_status()


def hermes_runtime_compatible(capabilities: object) -> bool:
    """Return whether a capability document supports the required standard APIs."""
    if not isinstance(capabilities, dict):
        return False
    features = capabilities.get("features")
    endpoints = capabilities.get("endpoints")
    if not isinstance(features, dict) or not isinstance(endpoints, dict):
        return False
    return all(features.get(name) is True for name in REQUIRED_HERMES_FEATURES) and all(
        name in endpoints for name in REQUIRED_HERMES_ENDPOINTS
    )


async def ensure_hermes_session_capability(agent_id: str) -> None:
    """Ensure that an agent exposes the standard Hermes run and session APIs."""
    try:
        async with httpx.AsyncClient(timeout=5, trust_env=False, follow_redirects=False) as client:
            capabilities = await HermesClient(client, agent_id).capabilities()
    except httpx.HTTPError as exc:
        raise RuntimeError("Agent runtime is unavailable") from exc
    if not hermes_runtime_compatible(capabilities):
        raise RuntimeError("Agent runtime does not expose the required Hermes session APIs")


def validate_hermes_session_id(value: object) -> str:
    """Validate a server-generated Hermes session identifier."""
    if not isinstance(value, str) or not HERMES_SESSION_ID_RE.fullmatch(value):
        raise RuntimeError("Invalid Hermes session ID")
    return value


async def mark_hermes_session_initialized(run_id: uuid.UUID, result: dict) -> None:
    """Mark a conversation session initialized after a successful first turn."""
    if str(result.get("status")) != "completed":
        return
    async with SessionLocal() as session:
        run = await session.get(AgentRun, run_id)
        if run is None:
            raise RuntimeError("Run disappeared before its Hermes session was finalized")
        runtime = await session.get(ConversationRuntime, run.conversation_id)
        if runtime is None or not runtime.hermes_session_id:
            raise RuntimeError("Conversation has no persistent Hermes session state")
        result_session_id = result.get("session_id")
        if result_session_id is not None:
            result_session_id = validate_hermes_session_id(result_session_id)
            if result_session_id != runtime.hermes_session_id:
                raise RuntimeError("Hermes returned a different session for this conversation")
        runtime.initialized_at = runtime.initialized_at or utcnow()
        runtime.updated_at = utcnow()
        await session.commit()


async def delete_hermes_session(agent_id: str, session_id: str) -> None:
    """Best-effort delete a persistent Hermes session."""
    validate_hermes_session_id(session_id)
    try:
        async with httpx.AsyncClient(timeout=20, trust_env=False, follow_redirects=False) as client:
            await delete_hermes_session_with_client(client, agent_id, session_id)
    except Exception as exc:
        logger.warning("Best-effort Hermes session deletion failed for %s: %s", session_id, exc)


async def delete_hermes_session_with_client(
    client: httpx.AsyncClient, agent_id: str, session_id: str
) -> None:
    """Delete a Hermes session with a caller-owned HTTP client."""
    await HermesClient(client, agent_id).delete_session(session_id)


async def create_hermes_session(client: httpx.AsyncClient, agent_id: str, session_id: str) -> None:
    """Create an empty persistent Hermes session for a first conversation turn."""
    await HermesClient(client, agent_id).create_session(session_id)


def normalize_hermes_history(messages: object) -> list[dict[str, str]]:
    """Convert persisted Hermes messages into the history accepted by Runs API."""
    if not isinstance(messages, list):
        raise TypeError("Hermes returned an invalid session message list")
    history: list[dict[str, str]] = []
    for message in messages:
        if not isinstance(message, dict):
            continue
        role = str(message.get("role") or "")
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            continue
        if role == "system":
            continue
        if role == "tool":
            tool_name = str(message.get("tool_name") or "tool")
            role = "assistant"
            content = f"[Tool result from {tool_name}]\n{content}"
        elif role not in {"user", "assistant"}:
            continue
        content = content.strip()
        if history and history[-1]["role"] == role:
            history[-1]["content"] += f"\n\n{content}"
        else:
            history.append({"role": role, "content": content})
    return history


async def fetch_hermes_history(
    client: httpx.AsyncClient, agent_id: str, session_id: str
) -> list[dict[str, str]]:
    """Fetch every persisted message for an initialized Hermes session."""
    return await HermesClient(client, agent_id).fetch_history(session_id)


async def prepare_hermes_history(
    client: httpx.AsyncClient,
    agent_id: str,
    session_id: str,
    initialized: bool,
) -> list[dict[str, str]]:
    """Create a first-turn session or load an initialized session transcript."""
    if initialized:
        return await fetch_hermes_history(client, agent_id, session_id)
    await delete_hermes_session_with_client(client, agent_id, session_id)
    await create_hermes_session(client, agent_id, session_id)
    return []


async def store_event(run_id: uuid.UUID, event_type: str, payload: dict) -> None:
    """Handle store event."""
    async with SessionLocal() as session:
        sequence = await session.scalar(
            select(func.coalesce(func.max(RunEvent.sequence), 0)).where(RunEvent.run_id == run_id)
        )
        session.add(
            RunEvent(
                run_id=run_id,
                sequence=int(sequence or 0) + 1,
                event_type=event_type[:80],
                payload=payload,
            )
        )
        await session.commit()


async def set_run_status(
    run_id: uuid.UUID, status: str, *, hermes_run_id: str | None = None, error: str | None = None
) -> None:
    """Set run status."""
    async with SessionLocal() as session:
        run = await session.get(AgentRun, run_id)
        if run is None:
            return
        run.status = status
        run.updated_at = utcnow()
        if hermes_run_id:
            run.hermes_run_id = hermes_run_id
        if error:
            run.error = error[:4000]
        await session.commit()


async def finalize_run(run_id: uuid.UUID, result: dict) -> None:
    """Handle finalize run."""
    final_status = str(result.get("status", "failed"))
    mapped = {
        "completed": RunStatus.completed.value,
        "cancelled": RunStatus.cancelled.value,
        "failed": RunStatus.failed.value,
    }.get(final_status, RunStatus.failed.value)
    async with SessionLocal() as session:
        run = await session.scalar(select(AgentRun).where(AgentRun.id == run_id).with_for_update())
        if run is None or run.finalized:
            return
        output = result.get("output")
        if output:
            session.add(
                Message(
                    conversation_id=run.conversation_id,
                    role="assistant",
                    content=str(output),
                )
            )
        conversation = await session.get(Conversation, run.conversation_id)
        if conversation:
            conversation.updated_at = utcnow()
        run.status = mapped
        run.updated_at = utcnow()
        run.finalized = True
        if result.get("error"):
            run.error = str(result["error"])[:4000]
        await session.commit()
    await store_event(run_id, f"run.{mapped}", result)


async def execute_run(run_id: uuid.UUID) -> None:
    """Execute run."""
    confidentiality_guard: RestrictedContentGuard | None = None
    workspace_before_run = {}
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
            agent = get_agent(run.agent_id)
            runtime = await session.get(ConversationRuntime, run.conversation_id)
            if runtime is None:
                raise RuntimeError("Conversation runtime state is unavailable")
            latest = await session.scalar(
                select(Message)
                .where(Message.conversation_id == run.conversation_id)
                .order_by(Message.created_at.desc(), Message.id.desc())
                .limit(1)
            )
            if latest is None or latest.role != "user":
                raise RuntimeError("Run has no current user message")
            if not runtime.hermes_session_id:
                raise RuntimeError("Conversation has no persistent Hermes session ID")
            confidentiality_guard = RestrictedContentGuard.build(
                agent.workspace_root,
                await protected_paths(session, agent.id),
            )
            run_input = latest.content
            if confidentiality_guard.active:
                run_input = f"{run_input}\n\n{RESTRICTED_TURN_REMINDER}"
            session_id = validate_hermes_session_id(runtime.hermes_session_id)
            first_turn = runtime.initialized_at is None
            workspace_before_run = snapshot_workspace(agent.workspace_root)

        timeout = httpx.Timeout(connect=15, read=None, write=60, pool=15)
        async with httpx.AsyncClient(
            timeout=timeout, trust_env=False, follow_redirects=False
        ) as client:
            history = await prepare_hermes_history(
                client,
                agent.id,
                session_id,
                initialized=not first_turn,
            )
            payload = {
                "input": run_input,
                "session_id": session_id,
                "conversation_history": history,
                "instructions": agent.instructions,
                "model": model_id_for_mode(agent.llm, run.model_mode),
                "provider": agent.llm.provider,
            }
            async with SessionLocal() as session:
                current_status = await session.scalar(
                    select(AgentRun.status).where(AgentRun.id == run_id)
                )
            if current_status != RunStatus.running.value:
                return
            response = await client.post(
                f"{str(agent.hermes_url).rstrip('/')}/v1/runs",
                headers=hermes_headers(agent.id),
                json=payload,
            )
            response.raise_for_status()
            hermes_run_id = response.json()["run_id"]
            async with SessionLocal() as session:
                current = await session.get(AgentRun, run_id)
                if current is None:
                    return
                should_continue = current.status == RunStatus.running.value
                current.hermes_run_id = hermes_run_id
                current.updated_at = utcnow()
                await session.commit()
            if not should_continue:
                await client.post(
                    f"{str(agent.hermes_url).rstrip('/')}/v1/runs/{hermes_run_id}/stop",
                    headers=hermes_headers(agent.id),
                )
                return
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
                        if confidentiality_guard.active and kind in TEXT_DELTA_EVENTS:
                            continue
                        await store_event(
                            run_id,
                            kind,
                            confidentiality_guard.sanitize_payload(event_payload),
                        )
                        if "approval" in kind and "response" not in kind:
                            await set_run_status(run_id, RunStatus.waiting_approval.value)
                        elif kind not in {"run.completed", "run.failed", "run.cancelled"}:
                            await set_run_status(run_id, RunStatus.running.value)

            status_response = await client.get(
                f"{str(agent.hermes_url).rstrip('/')}/v1/runs/{hermes_run_id}",
                headers=hermes_headers(agent.id),
            )
            status_response.raise_for_status()
            result = status_response.json()
            blocked = confidentiality_guard.remove_generated_derivatives(workspace_before_run)
            blocked_paths = tuple(item.relative_path for item in blocked)
            output = result.get("output")
            if isinstance(output, str):
                result["output"], output_changed = confidentiality_guard.sanitize_text(
                    output, blocked_paths
                )
            else:
                output_changed = False
            if blocked or output_changed:
                result["output"] = (
                    "I cannot create, copy, convert, or provide a download link for this "
                    "restricted analysis-only file. I can use it only to provide a limited "
                    "aggregate or answer a specific analytical question."
                )
                await store_event(
                    run_id,
                    "security.restricted_output_blocked",
                    {
                        "message": (
                            "A generated copy, download reference, or excessive reproduction of "
                            "restricted analysis-only content was blocked."
                        ),
                        "blocked_file_count": len(blocked),
                    },
                )
            await mark_hermes_session_initialized(run_id, result)
            await finalize_run(run_id, result)
    except asyncio.CancelledError:
        if confidentiality_guard is not None:
            confidentiality_guard.remove_generated_derivatives(workspace_before_run)
        await set_run_status(run_id, RunStatus.cancelled.value)
        raise
    except Exception as exc:
        if "first_turn" in locals() and first_turn and "session_id" in locals():
            await delete_hermes_session(run.agent_id, session_id)
        if confidentiality_guard is not None:
            blocked = confidentiality_guard.remove_generated_derivatives(workspace_before_run)
            if blocked:
                await store_event(
                    run_id,
                    "security.restricted_output_blocked",
                    {
                        "message": (
                            "A generated copy of restricted analysis-only content was blocked."
                        ),
                        "blocked_file_count": len(blocked),
                    },
                )
        await set_run_status(run_id, RunStatus.failed.value, error=str(exc))
        await store_event(run_id, "run.failed", {"error": str(exc)})


async def event_stream(run_id: uuid.UUID, after: int = 0) -> AsyncIterator[str]:
    """Handle event stream."""
    cursor = after
    idle_ticks = 0
    while True:
        async with SessionLocal() as session:
            events = list(
                (
                    await session.scalars(
                        select(RunEvent)
                        .where(RunEvent.run_id == run_id, RunEvent.sequence > cursor)
                        .order_by(RunEvent.sequence)
                    )
                ).all()
            )
            run = await session.get(AgentRun, run_id)
        for item in events:
            cursor = item.sequence
            data = json.dumps(
                {"sequence": item.sequence, "type": item.event_type, "payload": item.payload},
                ensure_ascii=False,
            )
            yield f"id: {item.sequence}\nevent: run-event\ndata: {data}\n\n"
        if events:
            idle_ticks = 0
        else:
            idle_ticks += 1
        if run is None or (run.status in TERMINAL_STATUSES and not events):
            yield f"event: stream-end\ndata: {json.dumps({'status': run.status if run else 'missing'})}\n\n"
            return
        if idle_ticks >= 20:
            yield ": keep-alive\n\n"
            idle_ticks = 0
        await asyncio.sleep(0.5)


async def stop_hermes_run(run: AgentRun) -> None:
    """Stop hermes run."""
    async with SessionLocal() as session:
        current = await session.get(AgentRun, run.id)
        if current is None or current.status not in ACTIVE_RUN_STATUSES:
            return
        hermes_run_id = current.hermes_run_id
        current.status = RunStatus.stopping.value if hermes_run_id else RunStatus.cancelled.value
        current.updated_at = utcnow()
        await session.commit()
    if not hermes_run_id:
        return
    async with httpx.AsyncClient(timeout=15, trust_env=False, follow_redirects=False) as client:
        await HermesClient(client, run.agent_id).stop_run(hermes_run_id)


async def approve_hermes_run(run: AgentRun, decision: str) -> None:
    """Handle approve hermes run."""
    if not run.hermes_run_id:
        raise RuntimeError("Hermes run is not initialized")
    async with httpx.AsyncClient(timeout=15, trust_env=False, follow_redirects=False) as client:
        await HermesClient(client, run.agent_id).approve_run(run.hermes_run_id, decision)
    await set_run_status(run.id, RunStatus.running.value)


async def recover_run(run_id: uuid.UUID) -> None:
    """Handle recover run."""
    async with SessionLocal() as session:
        run = await session.get(AgentRun, run_id)
        if run is None or not run.hermes_run_id:
            await set_run_status(
                run_id,
                RunStatus.failed.value,
                error="Backend restarted before Hermes accepted the run",
            )
            return
        agent = get_agent(run.agent_id)
        hermes_run_id = run.hermes_run_id
    try:
        async with httpx.AsyncClient(timeout=30, trust_env=False, follow_redirects=False) as client:
            while True:
                response = await client.get(
                    f"{str(agent.hermes_url).rstrip('/')}/v1/runs/{hermes_run_id}",
                    headers=hermes_headers(agent.id),
                )
                response.raise_for_status()
                result = response.json()
                status = str(result.get("status", "failed"))
                if status in {"completed", "failed", "cancelled"}:
                    await mark_hermes_session_initialized(run_id, result)
                    await finalize_run(run_id, result)
                    return
                mapped = (
                    RunStatus.waiting_approval.value
                    if "approval" in status
                    else RunStatus.running.value
                )
                await set_run_status(run_id, mapped)
                await asyncio.sleep(2)
    except Exception as exc:
        await set_run_status(run_id, RunStatus.failed.value, error=f"Run recovery failed: {exc}")
        await store_event(run_id, "run.failed", {"error": f"Run recovery failed: {exc}"})


async def recover_interrupted_runs() -> None:
    """Handle recover interrupted runs."""
    async with SessionLocal() as session:
        runs = list(
            (
                await session.scalars(
                    select(AgentRun).where(AgentRun.status.in_(ACTIVE_RUN_STATUSES))
                )
            ).all()
        )
        for run in runs:
            task = asyncio.create_task(recover_run(run.id))
            RECOVERY_TASKS.add(task)
            task.add_done_callback(RECOVERY_TASKS.discard)
