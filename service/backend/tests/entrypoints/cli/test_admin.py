"""Characterize administrative CLI behavior before package migration."""

import io
import json
import subprocess
import sys
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from entrypoints.cli import admin as cli
from infrastructure.database.models import (
    AgentRun,
    Conversation,
    ConversationRuntime,
    Message,
    RunEvent,
    User,
    WorkspacePathPolicy,
)


def test_admin_entrypoint_registers_all_feature_database_models() -> None:
    """Register feature-owned tables before CLI database initialization runs."""
    script = """
from entrypoints.cli import admin
from sqlalchemy.orm import configure_mappers
from infrastructure.database.models import Base

configure_mappers()
required = {'metabase_planning_states', 'metabase_planning_operations'}
assert required <= set(Base.metadata.tables)
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr


@pytest.fixture
def cli_runtime(database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """Bind CLI persistence and configured agent lookup to a disposable test runtime."""
    workspace = tmp_path / "assistant" / "workspace"
    workspace.mkdir(parents=True)
    configured = SimpleNamespace(id="assistant", workspace_root=workspace)
    monkeypatch.setattr(cli, "SessionLocal", database)
    monkeypatch.setattr(cli, "initialize_database", lambda: _async_noop())
    monkeypatch.setattr(
        cli, "get_agent", lambda agent_id: configured if agent_id == "assistant" else _missing()
    )
    return configured


async def _async_noop() -> None:
    """Provide a no-op awaitable for already-initialized test schemas."""


def _missing() -> None:
    """Raise the same category used by unknown manifest lookups."""
    raise LookupError("unknown agent")


@pytest.mark.integration
async def test_cli_creates_and_updates_regular_and_administrator_users(
    cli_runtime, database
) -> None:
    """Preserve explicit account creation, update, role assignment, and password validation."""
    await cli.create_user("assistant-user", "assistant", "sk", "long enough password\n")
    await cli.create_user("assistant-user", "assistant", "en", "another long password")
    await cli.create_admin("owner", "en", "administrator password")
    await cli.create_admin("owner", "sk", "updated administrator password")
    async with database() as session:
        users = {item.username: item for item in (await session.scalars(select(User))).all()}
    assert users["assistant-user"].agent_id == "assistant"
    assert users["assistant-user"].locale == "en"
    assert users["assistant-user"].is_admin is False
    assert users["owner"].agent_id is None
    assert users["owner"].is_admin is True
    with pytest.raises(SystemExit, match="12"):
        await cli.create_user("short", "assistant", "en", "short")
    with pytest.raises(LookupError):
        await cli.create_user("unknown", "missing", "en", "long enough password")


@pytest.mark.integration
async def test_cli_interactive_password_and_missing_import_user_contracts(
    cli_runtime, database, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Preserve interactive password handling and import destination validation."""
    prompts = iter(["interactive password", "interactive password"])
    monkeypatch.setattr(cli.getpass, "getpass", lambda _: next(prompts))
    await cli.create_user("interactive", "assistant", "en")
    admin_prompts = iter(["interactive administrator", "interactive administrator"])
    monkeypatch.setattr(cli.getpass, "getpass", lambda _: next(admin_prompts))
    await cli.create_admin("interactive-admin", "en")
    async with database() as session:
        created = await session.scalar(select(User).where(User.username == "interactive"))
    assert created is not None
    monkeypatch.setattr(
        sys,
        "stdin",
        io.StringIO(json.dumps({"version": 1, "agent_id": "assistant"})),
    )
    with pytest.raises(SystemExit, match="destination web user"):
        await cli.import_history("assistant", "missing")
    mismatch = iter(["first password", "second password"])
    monkeypatch.setattr(cli.getpass, "getpass", lambda _: next(mismatch))
    with pytest.raises(SystemExit, match="do not match"):
        await cli.create_user("mismatch", "assistant", "en")
    with pytest.raises(SystemExit, match="12"):
        await cli.create_admin("short-admin", "en", "short")


@pytest.mark.integration
async def test_cli_export_import_round_trip_preserves_history_contract(
    cli_runtime, database, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Preserve JSON archive shape and safe import of non-terminal historical runs."""
    async with database() as session:
        user = User(username="assistant-user", password_hash="unused", agent_id="assistant")
        session.add(user)
        await session.flush()
        conversation = Conversation(user_id=user.id, agent_id="assistant", title="Question")
        session.add(conversation)
        await session.flush()
        session.add(
            ConversationRuntime(conversation_id=conversation.id, hermes_session_id="session_1")
        )
        session.add(Message(conversation_id=conversation.id, role="user", content="Question"))
        run = AgentRun(
            conversation_id=conversation.id, user_id=user.id, agent_id="assistant", status="running"
        )
        session.add(run)
        await session.flush()
        session.add(RunEvent(run_id=run.id, sequence=1, event_type="run.started", payload={}))
        session.add(WorkspacePathPolicy(agent_id="assistant", path="restricted.xlsx"))
        await session.commit()

    output = io.StringIO()
    with redirect_stdout(output):
        await cli.export_history("assistant")
    archive = json.loads(output.getvalue())
    assert archive["version"] == cli.HISTORY_FORMAT_VERSION
    assert archive["runtimes"][0]["hermes_session_id"] == "session_1"
    assert archive["workspace_policies"] == [{"path": "restricted.xlsx", "no_user_access": True}]

    async with database() as session:
        await session.execute(__import__("sqlalchemy").delete(Conversation))
        await session.execute(__import__("sqlalchemy").delete(WorkspacePathPolicy))
        await session.commit()
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(archive)))
    recorded: list[str] = []

    async def record_policy(_, agent_id: str, __: Path) -> None:
        """Record policy regeneration at the end of a successful import."""
        recorded.append(agent_id)

    monkeypatch.setattr(cli, "write_agent_policy_file", record_policy)
    await cli.import_history("assistant", "assistant-user")
    async with database() as session:
        imported_run = await session.scalar(select(AgentRun))
        imported_runtime = await session.scalar(select(ConversationRuntime))
    assert imported_run.status == "failed"
    assert imported_runtime.hermes_session_id == "session_1"
    assert recorded == ["assistant"]


@pytest.mark.unit
async def test_cli_rejects_invalid_archives_and_password_confirmation(
    cli_runtime, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Preserve CLI failures for invalid archives and interactive password mismatch."""
    monkeypatch.setattr(sys, "stdin", io.StringIO('{"version": 99, "agent_id": "assistant"}'))
    with pytest.raises(SystemExit, match="does not match"):
        await cli.import_history("assistant", "assistant-user")
    prompts = iter(["password one", "password two"])
    monkeypatch.setattr(cli.getpass, "getpass", lambda _: next(prompts))
    with pytest.raises(SystemExit, match="do not match"):
        await cli.create_admin("owner", "en")


@pytest.mark.unit
def test_cli_main_dispatches_every_public_command(monkeypatch: pytest.MonkeyPatch) -> None:
    """Preserve parser arguments and dispatch targets for all CLI subcommands."""

    def fake_run(coroutine) -> None:
        """Await and classify dispatch coroutines without creating a real event loop."""
        coroutine.close()

    monkeypatch.setattr(cli.asyncio, "run", fake_run)
    monkeypatch.setattr(sys, "stdin", io.StringIO("password from stdin\n"))
    for arguments in (
        ["migrate"],
        ["create-user", "u", "assistant", "--locale", "sk", "--password-stdin"],
        ["create-admin", "owner", "--password-stdin"],
        ["export-history", "assistant"],
        ["import-history", "assistant", "u"],
    ):
        monkeypatch.setattr(sys, "argv", ["open-agent-workspace-ai-admin", *arguments])
        cli.main()

    monkeypatch.setattr(
        cli.argparse.ArgumentParser,
        "parse_args",
        lambda _: SimpleNamespace(command="unsupported"),
    )
    cli.main()
