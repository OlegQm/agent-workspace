"""Provide administrative commands for users and agent history."""

import argparse
import asyncio
import getpass
import json
import sys
import uuid
from datetime import datetime

from sqlalchemy import select

from features.agents.infrastructure.configuration.registry import get_agent
from features.identity.application.authentication import password_hash
from features.metabase_planning.infrastructure.persistence.models import (
    MetabasePlanningOperation,
    MetabasePlanningState,
)
from features.workspace.application.policies.operations import write_agent_policy_file
from infrastructure.database.initialization import initialize_database
from infrastructure.database.models import (
    AgentRun,
    Conversation,
    ConversationRuntime,
    Message,
    RunEvent,
    User,
    WorkspacePathPolicy,
)
from infrastructure.database.session import SessionLocal

HISTORY_FORMAT_VERSION = 1
FEATURE_DATABASE_MODELS = (MetabasePlanningOperation, MetabasePlanningState)


async def create_user(
    username: str,
    agent_id: str,
    locale: str,
    supplied_password: str | None = None,
) -> None:
    """Explicitly create or update a regular agent account."""
    get_agent(agent_id)
    if supplied_password is None:
        password = getpass.getpass("Password: ")
        confirmation = getpass.getpass("Repeat password: ")
        if password != confirmation:
            raise SystemExit("Passwords do not match")
    else:
        password = supplied_password.rstrip("\n")
    if len(password) < 12:
        raise SystemExit("Password must contain at least 12 characters")
    await initialize_database()
    async with SessionLocal() as session:
        existing = await session.scalar(select(User).where(User.username == username))
        if existing:
            existing.password_hash = password_hash.hash(password)
            existing.agent_id = agent_id
            existing.locale = locale
            existing.is_active = True
            existing.is_admin = False
        else:
            session.add(
                User(
                    username=username,
                    password_hash=password_hash.hash(password),
                    agent_id=agent_id,
                    locale=locale,
                    is_admin=False,
                )
            )
        await session.commit()


async def create_admin(
    username: str,
    locale: str,
    supplied_password: str | None = None,
) -> None:
    """Explicitly create or update an account with administrator privileges."""
    if supplied_password is None:
        password = getpass.getpass("Password: ")
        confirmation = getpass.getpass("Repeat password: ")
        if password != confirmation:
            raise SystemExit("Passwords do not match")
    else:
        password = supplied_password.rstrip("\n")
    if len(password) < 12:
        raise SystemExit("Password must contain at least 12 characters")
    await initialize_database()
    async with SessionLocal() as session:
        existing = await session.scalar(select(User).where(User.username == username))
        if existing:
            existing.password_hash = password_hash.hash(password)
            existing.agent_id = None
            existing.locale = locale
            existing.is_active = True
            existing.is_admin = True
        else:
            session.add(
                User(
                    username=username,
                    password_hash=password_hash.hash(password),
                    agent_id=None,
                    locale=locale,
                    is_admin=True,
                )
            )
        await session.commit()


async def export_history(agent_id: str) -> None:
    """Export history."""
    get_agent(agent_id)
    async with SessionLocal() as session:
        conversations = list(
            (
                await session.scalars(select(Conversation).where(Conversation.agent_id == agent_id))
            ).all()
        )
        conversation_ids = [item.id for item in conversations]
        runtimes = (
            list(
                (
                    await session.scalars(
                        select(ConversationRuntime).where(
                            ConversationRuntime.conversation_id.in_(conversation_ids)
                        )
                    )
                ).all()
            )
            if conversation_ids
            else []
        )
        messages = (
            list(
                (
                    await session.scalars(
                        select(Message).where(Message.conversation_id.in_(conversation_ids))
                    )
                ).all()
            )
            if conversation_ids
            else []
        )
        runs = list(
            (await session.scalars(select(AgentRun).where(AgentRun.agent_id == agent_id))).all()
        )
        run_ids = [item.id for item in runs]
        events = (
            list(
                (await session.scalars(select(RunEvent).where(RunEvent.run_id.in_(run_ids)))).all()
            )
            if run_ids
            else []
        )
        users = list((await session.scalars(select(User).where(User.agent_id == agent_id))).all())
        policies = list(
            (
                await session.scalars(
                    select(WorkspacePathPolicy).where(WorkspacePathPolicy.agent_id == agent_id)
                )
            ).all()
        )
    payload = {
        "version": HISTORY_FORMAT_VERSION,
        "agent_id": agent_id,
        "users": [
            {"id": str(item.id), "username": item.username, "locale": item.locale} for item in users
        ],
        "conversations": [
            {
                "id": str(item.id),
                "user_id": str(item.user_id),
                "title": item.title,
                "created_at": item.created_at.isoformat(),
                "updated_at": item.updated_at.isoformat(),
            }
            for item in conversations
        ],
        "runtimes": [
            {
                "conversation_id": str(item.conversation_id),
                "hermes_session_id": item.hermes_session_id,
                "initialized_at": (
                    item.initialized_at.isoformat() if item.initialized_at else None
                ),
                "created_at": item.created_at.isoformat(),
                "updated_at": item.updated_at.isoformat(),
            }
            for item in runtimes
        ],
        "messages": [
            {
                "id": str(item.id),
                "conversation_id": str(item.conversation_id),
                "role": item.role,
                "content": item.content,
                "attachments": item.attachments,
                "created_at": item.created_at.isoformat(),
            }
            for item in messages
        ],
        "runs": [
            {
                "id": str(item.id),
                "conversation_id": str(item.conversation_id),
                "user_id": str(item.user_id),
                "status": item.status,
                "model_mode": item.model_mode,
                "error": item.error,
                "created_at": item.created_at.isoformat(),
                "updated_at": item.updated_at.isoformat(),
            }
            for item in runs
        ],
        "events": [
            {
                "run_id": str(item.run_id),
                "sequence": item.sequence,
                "event_type": item.event_type,
                "payload": item.payload,
                "created_at": item.created_at.isoformat(),
            }
            for item in events
        ],
        "workspace_policies": [
            {"path": item.path, "no_user_access": item.no_user_access} for item in policies
        ],
    }
    json.dump(payload, sys.stdout, ensure_ascii=False)


async def import_history(agent_id: str, username: str) -> None:
    """Import history."""
    payload = json.load(sys.stdin)
    if payload.get("version") != HISTORY_FORMAT_VERSION or payload.get("agent_id") != agent_id:
        raise SystemExit("History archive does not match the requested agent")
    async with SessionLocal() as session:
        user = await session.scalar(
            select(User).where(User.username == username, User.agent_id == agent_id)
        )
        if user is None:
            raise SystemExit("Create the destination web user before importing history")
        user_ids = {item["id"]: user.id for item in payload.get("users", [])}
        for item in payload.get("conversations", []):
            session.add(
                Conversation(
                    id=uuid.UUID(item["id"]),
                    user_id=user_ids.get(item["user_id"], user.id),
                    agent_id=agent_id,
                    title=item["title"],
                    created_at=datetime.fromisoformat(item["created_at"]),
                    updated_at=datetime.fromisoformat(item["updated_at"]),
                )
            )
        await session.flush()
        for item in payload.get("runtimes", []):
            session.add(
                ConversationRuntime(
                    conversation_id=uuid.UUID(item["conversation_id"]),
                    hermes_session_id=item.get("hermes_session_id"),
                    initialized_at=(
                        datetime.fromisoformat(item["initialized_at"])
                        if item.get("initialized_at")
                        else None
                    ),
                    created_at=datetime.fromisoformat(item["created_at"]),
                    updated_at=datetime.fromisoformat(item["updated_at"]),
                )
            )
        for item in payload.get("messages", []):
            session.add(
                Message(
                    id=uuid.UUID(item["id"]),
                    conversation_id=uuid.UUID(item["conversation_id"]),
                    role=item["role"],
                    content=item["content"],
                    attachments=item.get("attachments", []),
                    created_at=datetime.fromisoformat(item["created_at"]),
                )
            )
        for item in payload.get("runs", []):
            session.add(
                AgentRun(
                    id=uuid.UUID(item["id"]),
                    conversation_id=uuid.UUID(item["conversation_id"]),
                    user_id=user_ids.get(item["user_id"], user.id),
                    agent_id=agent_id,
                    model_mode=item.get("model_mode", "medium"),
                    status=item["status"]
                    if item["status"] not in {"queued", "running", "waiting_approval", "stopping"}
                    else "failed",
                    error=item.get("error"),
                    created_at=datetime.fromisoformat(item["created_at"]),
                    updated_at=datetime.fromisoformat(item["updated_at"]),
                )
            )
        for item in payload.get("events", []):
            session.add(
                RunEvent(
                    run_id=uuid.UUID(item["run_id"]),
                    sequence=item["sequence"],
                    event_type=item["event_type"],
                    payload=item["payload"],
                    created_at=datetime.fromisoformat(item["created_at"]),
                )
            )
        for item in payload.get("workspace_policies", []):
            session.add(
                WorkspacePathPolicy(
                    agent_id=agent_id,
                    path=item["path"],
                    no_user_access=item.get("no_user_access", True),
                )
            )
        await session.commit()
        await write_agent_policy_file(session, agent_id, get_agent(agent_id).workspace_root)


def main() -> None:
    """Run the command-line entry point."""
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("migrate")
    create = subparsers.add_parser("create-user")
    create.add_argument("username")
    create.add_argument("agent_id")
    create.add_argument("--locale", choices=["en", "sk"], default="en")
    create.add_argument("--password-stdin", action="store_true")
    admin = subparsers.add_parser("create-admin")
    admin.add_argument("username")
    admin.add_argument("--locale", choices=["en", "sk"], default="en")
    admin.add_argument("--password-stdin", action="store_true")
    export = subparsers.add_parser("export-history")
    export.add_argument("agent_id")
    restore = subparsers.add_parser("import-history")
    restore.add_argument("agent_id")
    restore.add_argument("username")
    args = parser.parse_args()
    if args.command == "migrate":
        asyncio.run(initialize_database())
    elif args.command == "create-user":
        password = sys.stdin.readline() if args.password_stdin else None
        asyncio.run(
            create_user(
                args.username,
                args.agent_id,
                args.locale,
                password,
            )
        )
    elif args.command == "create-admin":
        password = sys.stdin.readline() if args.password_stdin else None
        asyncio.run(create_admin(args.username, args.locale, password))
    elif args.command == "export-history":
        asyncio.run(export_history(args.agent_id))
    elif args.command == "import-history":
        asyncio.run(import_history(args.agent_id, args.username))
