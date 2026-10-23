"""Test planning conversation creation and correction persistence."""

import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from features.metabase_planning.application.turns import (
    PlanningTurnCommand,
    queue_correction,
    queue_initial_turn,
)
from features.metabase_planning.domain.exceptions import (
    PlanningConflict,
    PlanningConversationNotFound,
    StalePlanningState,
)
from features.metabase_planning.infrastructure.persistence.models import MetabasePlanningState
from infrastructure.database.models import Message, User


def agent(workspace: Path) -> SimpleNamespace:
    """Build the workspace boundary required by planning turns."""
    return SimpleNamespace(id="assistant", workspace_root=workspace)


@pytest.mark.integration
async def test_initial_turn_persists_marked_chat_without_injecting_file_content(
    users: tuple[User, User], database, tmp_path: Path
) -> None:
    """Store attachment references without appending paths or contents to the message."""
    workspace = tmp_path / "workspace"
    workspace.mkdir(exist_ok=True)
    workspace.joinpath("example.xlsx").write_bytes(b"context")
    command = PlanningTurnCommand(
        content="Build monthly revenue",
        attachments=["example.xlsx"],
        model_mode="medium",
    )

    async with database() as session:
        conversation, run = await queue_initial_turn(command, users[0], agent(workspace), session)
        message = await session.scalar(
            select(Message).where(Message.conversation_id == conversation.id)
        )
        state = await session.get(MetabasePlanningState, conversation.id)

    assert conversation.kind == "metabase_planning"
    assert run.status == "queued"
    assert message.content == "Build monthly revenue"
    assert message.attachments == ["example.xlsx"]
    assert state.workflow_state == "collecting"


@pytest.mark.integration
async def test_correction_invalidates_actions_before_queuing_hermes(
    users: tuple[User, User], database, tmp_path: Path
) -> None:
    """Persist revision invalidation in the same transaction as the correction."""
    workspace = tmp_path / "workspace"
    workspace.mkdir(exist_ok=True)
    command = PlanningTurnCommand(content="Initial", attachments=[], model_mode="medium")
    async with database() as session:
        conversation, first_run = await queue_initial_turn(
            command, users[0], agent(workspace), session
        )
        first_run.status = "completed"
        state = await session.get(MetabasePlanningState, conversation.id)
        state.workflow_state = "plan_ready"
        state.plan_revision = 1
        state.plan_for_requirements_revision = 0
        state.structured_plan = {"business_question": {"text": "Old"}}
        await session.commit()

        run = await queue_correction(
            conversation.id,
            PlanningTurnCommand(
                content="Use weekly grain",
                attachments=[],
                model_mode="high",
                workflow_version=0,
            ),
            users[0],
            agent(workspace),
            session,
        )
        await session.refresh(state)

    assert run.model_mode == "high"
    assert state.workflow_state == "collecting"
    assert state.requirements_revision == 1
    assert state.workflow_version == 1
    assert state.structured_plan is None


@pytest.mark.integration
async def test_correction_rejects_stale_workflow_version(
    users: tuple[User, User], database, tmp_path: Path
) -> None:
    """Reject an old browser tab without writing its message."""
    workspace = tmp_path / "workspace"
    workspace.mkdir(exist_ok=True)
    async with database() as session:
        conversation, _ = await queue_initial_turn(
            PlanningTurnCommand(content="Initial", attachments=[], model_mode="medium"),
            users[0],
            agent(workspace),
            session,
        )
        with pytest.raises(StalePlanningState):
            await queue_correction(
                conversation.id,
                PlanningTurnCommand(
                    content="Stale",
                    attachments=[],
                    model_mode="medium",
                    workflow_version=9,
                ),
                users[0],
                agent(workspace),
                session,
            )
        count = len(
            list(
                await session.scalars(
                    select(Message).where(Message.conversation_id == conversation.id)
                )
            )
        )

    assert count == 1


@pytest.mark.integration
async def test_correction_hides_foreign_or_non_planning_conversation(
    users: tuple[User, User], database, tmp_path: Path
) -> None:
    """Require an owned marked planning conversation before any correction write."""
    workspace = tmp_path / "workspace"
    workspace.mkdir(exist_ok=True)
    async with database() as session:
        with pytest.raises(PlanningConversationNotFound):
            await queue_correction(
                uuid.uuid4(),
                PlanningTurnCommand(
                    content="Missing",
                    attachments=[],
                    model_mode="medium",
                    workflow_version=0,
                ),
                users[0],
                agent(workspace),
                session,
            )


@pytest.mark.unit
async def test_run_commit_translates_active_agent_constraint() -> None:
    """Expose one stable conflict when PostgreSQL rejects a second active run."""
    from sqlalchemy.exc import IntegrityError

    from features.metabase_planning.application import turns

    class Session:
        """Raise the relevant SQLAlchemy error from commit."""

        async def commit(self) -> None:
            """Simulate the unique active-run constraint."""
            raise IntegrityError("statement", {}, RuntimeError("duplicate"))

        async def rollback(self) -> None:
            """Accept rollback after the failed commit."""

    with pytest.raises(PlanningConflict, match="active run"):
        await turns._commit_run(Session(), object())  # type: ignore[arg-type]
