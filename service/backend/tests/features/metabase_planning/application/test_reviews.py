"""Test idempotent YouTrack review submission and safe serialization."""

import uuid
from dataclasses import dataclass, field
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from features.metabase_planning.application.reviews import (
    ReviewCommand,
    ReviewIssue,
    ReviewIssueNotFound,
    ReviewSubmissionRejected,
    ReviewSubmissionUnavailable,
    build_review_description,
    submit_for_review,
)
from features.metabase_planning.domain.exceptions import (
    PlanningConflict,
    PlanningConversationNotFound,
    StalePlanningState,
)
from features.metabase_planning.domain.models import StructuredPlan
from features.metabase_planning.infrastructure.persistence.models import (
    MetabasePlanningOperation,
    MetabasePlanningState,
)
from infrastructure.database.models import Conversation, User


def _plan(text: str = "Monthly paid revenue") -> StructuredPlan:
    """Return a complete plan made only from confirmed business statements."""
    item = {"text": text, "provenance": "user_confirmed"}
    return StructuredPlan.model_validate(
        {
            "business_question": item,
            "metrics": [item],
            "sources": [item],
            "period": [item],
            "grain": [item],
            "dimensions": [],
            "filters": [],
            "comparisons": [],
            "exclusions": [],
            "visualization": [item],
            "expected_interpretation": [],
            "assumptions": [],
            "explicit_answers": [],
        }
    )


@dataclass
class FakeReviewGateway:
    """Record external review operations without network access."""

    creates: list[tuple[str, str]] = field(default_factory=list)
    updates: list[tuple[str, str, str]] = field(default_factory=list)

    async def create_issue(self, summary: str, description: str) -> ReviewIssue:
        """Return one deterministic fake issue."""
        self.creates.append((summary, description))
        return ReviewIssue(id="2-7", key="BI-7", status="Open")

    async def update_issue(self, issue_id: str, description: str, comment: str) -> ReviewIssue:
        """Return the same deterministic fake issue after replacement."""
        self.updates.append((issue_id, description, comment))
        return ReviewIssue(id=issue_id, key="BI-7", status="In Progress")


def test_review_description_contains_only_structured_business_plan() -> None:
    """Never serialize chat messages, attachment paths, or file-derived statements."""
    description = build_review_description(_plan())
    assert "Monthly paid revenue" in description
    assert "Business question" in description

    with pytest.raises(ValueError, match="workspace or external references"):
        build_review_description(_plan("workspace/report.xlsx"))


async def _ready_state(database, user: User, *, issue_id: str | None = None):
    """Persist one current sendable plan."""
    plan = _plan()
    async with database() as session:
        conversation = Conversation(
            user_id=user.id,
            agent_id="assistant",
            title="Revenue",
            kind="metabase_planning",
        )
        session.add(conversation)
        await session.flush()
        session.add(
            MetabasePlanningState(
                conversation_id=conversation.id,
                workflow_state="plan_ready",
                workflow_version=3,
                plan_revision=1,
                plan_for_requirements_revision=0,
                structured_plan=plan.model_dump(mode="json"),
                youtrack_issue_id=issue_id,
                youtrack_issue_key="BI-7" if issue_id else None,
            )
        )
        await session.commit()
        return conversation.id


@pytest.mark.integration
async def test_create_review_is_idempotent_and_records_server_issue_link(database, users) -> None:
    """Create no more than one issue for a confirmed plan command."""
    conversation_id = await _ready_state(database, users[0])
    gateway = FakeReviewGateway()
    agent = SimpleNamespace(id="assistant")
    command = ReviewCommand(workflow_version=3, plan_revision=1, idempotency_key="tap-1")

    async with database() as session:
        first = await submit_for_review(
            session, conversation_id, users[0], agent, command, gateway
        )
    async with database() as session:
        second = await submit_for_review(
            session, conversation_id, users[0], agent, command, gateway
        )

    assert first.youtrack_issue_key == second.youtrack_issue_key == "BI-7"
    assert len(gateway.creates) == 1
    assert gateway.creates[0][0] == (
        "[AI GENERATED METABASE CHART PLAN] Monthly paid revenue"
    )
    async with database() as session:
        operations = list(
            await session.scalars(
                select(MetabasePlanningOperation).where(
                    MetabasePlanningOperation.conversation_id == conversation_id
                )
            )
        )
        assert [operation.status for operation in operations] == ["completed"]


@pytest.mark.integration
async def test_later_plan_replaces_same_issue_and_adds_revision_comment(database, users) -> None:
    """Update the linked issue instead of creating a duplicate."""
    conversation_id = await _ready_state(database, users[0], issue_id="2-7")
    gateway = FakeReviewGateway()

    async with database() as session:
        state = await submit_for_review(
            session,
            conversation_id,
            users[0],
            SimpleNamespace(id="assistant"),
            ReviewCommand(workflow_version=3, plan_revision=1, idempotency_key="tap-2"),
            gateway,
        )

    assert gateway.creates == []
    assert gateway.updates[0][0] == "2-7"
    assert "revision 1" in gateway.updates[0][2].lower()
    assert state.issue_status == "In Progress"


@pytest.mark.integration
async def test_missing_linked_issue_is_recreated_and_relinked(database, users) -> None:
    """Create and persist a replacement when YouTrack confirms the linked issue is gone."""
    conversation_id = await _ready_state(database, users[0], issue_id="2-deleted")

    class MissingIssueGateway(FakeReviewGateway):
        """Report a confirmed missing issue before creating its replacement."""

        async def update_issue(
            self,
            issue_id: str,
            description: str,
            comment: str,
        ) -> ReviewIssue:
            """Record the attempted update and prove that its target does not exist."""
            self.updates.append((issue_id, description, comment))
            raise ReviewIssueNotFound("linked issue is missing")

        async def create_issue(self, summary: str, description: str) -> ReviewIssue:
            """Create a deterministic replacement issue."""
            self.creates.append((summary, description))
            return ReviewIssue(id="2-9", key="BI-9", status="Open")

    gateway = MissingIssueGateway()
    async with database() as session:
        state = await submit_for_review(
            session,
            conversation_id,
            users[0],
            SimpleNamespace(id="assistant"),
            ReviewCommand(workflow_version=3, plan_revision=1, idempotency_key="recreate"),
            gateway,
        )

    assert gateway.updates[0][0] == "2-deleted"
    assert len(gateway.creates) == 1
    assert gateway.creates[0][0] == (
        "[AI GENERATED METABASE CHART PLAN] Monthly paid revenue"
    )
    assert state.youtrack_issue_id == "2-9"
    assert state.youtrack_issue_key == "BI-9"
    async with database() as session:
        operation = await session.scalar(
            select(MetabasePlanningOperation).where(
                MetabasePlanningOperation.conversation_id == conversation_id
            )
        )
    assert operation.operation_type == "review_recreate"
    assert operation.status == "completed"


@pytest.mark.integration
async def test_uncertain_create_failure_blocks_automatic_duplicate_retry(database, users) -> None:
    """Persist unknown outcomes and fail closed rather than creating twice."""
    conversation_id = await _ready_state(database, users[0])

    class FailingGateway(FakeReviewGateway):
        """Simulate loss of a create response after an external write may have happened."""

        async def create_issue(self, summary: str, description: str) -> ReviewIssue:
            """Raise an unavailable result without exposing an error body."""
            raise ReviewSubmissionUnavailable("review service unavailable")

    command = ReviewCommand(workflow_version=3, plan_revision=1, idempotency_key="tap-3")
    async with database() as session:
        with pytest.raises(ReviewSubmissionUnavailable):
            await submit_for_review(
                session,
                conversation_id,
                users[0],
                SimpleNamespace(id="assistant"),
                command,
                FailingGateway(),
            )
    async with database() as session:
        operation = await session.scalar(
            select(MetabasePlanningOperation).where(
                MetabasePlanningOperation.conversation_id == conversation_id
            )
        )
        assert operation.status == "outcome_unknown"


@pytest.mark.integration
async def test_pending_review_is_durable_before_the_external_write(database, users) -> None:
    """Commit the audit record before the request can create a remote issue."""
    conversation_id = await _ready_state(database, users[0])

    class InspectingGateway(FakeReviewGateway):
        """Inspect persistence from a separate transaction during the external call."""

        async def create_issue(self, summary: str, description: str) -> ReviewIssue:
            """Require a visible pending operation before returning success."""
            async with database() as other:
                operation = await other.scalar(
                    select(MetabasePlanningOperation).where(
                        MetabasePlanningOperation.conversation_id == conversation_id
                    )
                )
                assert operation is not None
                assert operation.status == "pending"
            return await super().create_issue(summary, description)

    async with database() as session:
        await submit_for_review(
            session,
            conversation_id,
            users[0],
            SimpleNamespace(id="assistant"),
            ReviewCommand(workflow_version=3, plan_revision=1, idempotency_key="durable"),
            InspectingGateway(),
        )


@pytest.mark.integration
async def test_known_rejection_can_retry_the_same_idempotency_key(database, users) -> None:
    """Retry only when the transport proves that no remote issue was created."""
    conversation_id = await _ready_state(database, users[0])

    class RetryGateway(FakeReviewGateway):
        """Reject the first request definitively and accept the second."""

        attempts = 0

        async def create_issue(self, summary: str, description: str) -> ReviewIssue:
            """Return a known-safe rejection once."""
            self.attempts += 1
            if self.attempts == 1:
                raise ReviewSubmissionRejected("request rejected")
            return await super().create_issue(summary, description)

    gateway = RetryGateway()
    command = ReviewCommand(workflow_version=3, plan_revision=1, idempotency_key="retry")
    async with database() as session:
        with pytest.raises(ReviewSubmissionRejected):
            await submit_for_review(
                session,
                conversation_id,
                users[0],
                SimpleNamespace(id="assistant"),
                command,
                gateway,
            )
    async with database() as session:
        state = await submit_for_review(
            session,
            conversation_id,
            users[0],
            SimpleNamespace(id="assistant"),
            command,
            gateway,
        )

    assert state.youtrack_issue_key == "BI-7"
    async with database() as session:
        operation = await session.scalar(
            select(MetabasePlanningOperation).where(
                MetabasePlanningOperation.conversation_id == conversation_id
            )
        )
        assert operation.status == "completed"
        assert operation.attempt_count == 2


@pytest.mark.integration
async def test_active_review_operation_blocks_another_client_key(database, users) -> None:
    """Prevent concurrent tabs from creating duplicate issues with different keys."""
    conversation_id = await _ready_state(database, users[0])
    async with database() as session:
        session.add(
            MetabasePlanningOperation(
                conversation_id=conversation_id,
                operation_type="review_create",
                idempotency_key="first-tab",
                requirements_revision=0,
                plan_revision=1,
                status="pending",
                attempt_count=1,
            )
        )
        await session.commit()

    async with database() as session:
        with pytest.raises(Exception, match="already in progress"):
            await submit_for_review(
                session,
                conversation_id,
                users[0],
                SimpleNamespace(id="assistant"),
                ReviewCommand(workflow_version=3, plan_revision=1, idempotency_key="second-tab"),
                FakeReviewGateway(),
            )


@pytest.mark.integration
async def test_completed_old_request_does_not_submit_a_newer_plan_revision(database, users) -> None:
    """Link the issue while preserving a plan revised during the external request."""
    conversation_id = await _ready_state(database, users[0])

    class ConcurrentRevisionGateway(FakeReviewGateway):
        """Persist a newer ready plan before the older external call returns."""

        async def create_issue(self, summary: str, description: str) -> ReviewIssue:
            """Simulate another completed planning turn in a separate transaction."""
            async with database() as other:
                state = await other.get(MetabasePlanningState, conversation_id)
                state.requirements_revision = 1
                state.workflow_version = 5
                state.plan_revision = 2
                state.plan_for_requirements_revision = 1
                state.workflow_state = "plan_ready"
                state.structured_plan = _plan("Weekly paid revenue").model_dump(mode="json")
                await other.commit()
            return await super().create_issue(summary, description)

    async with database() as session:
        state = await submit_for_review(
            session,
            conversation_id,
            users[0],
            SimpleNamespace(id="assistant"),
            ReviewCommand(workflow_version=3, plan_revision=1, idempotency_key="old-plan"),
            ConcurrentRevisionGateway(),
        )

    assert state.workflow_state == "plan_ready"
    assert state.plan_revision == 2
    assert state.last_submitted_plan_revision == 1


@pytest.mark.integration
async def test_review_rejects_missing_stale_and_existing_uncertain_operations(database, users) -> None:
    """Fail before an external write when ownership, revision, or outcome is unsafe."""
    agent = SimpleNamespace(id="assistant")
    gateway = FakeReviewGateway()
    async with database() as session:
        with pytest.raises(PlanningConversationNotFound):
            await submit_for_review(
                session,
                uuid.uuid4(),
                users[0],
                agent,
                ReviewCommand(0, 1, "missing"),
                gateway,
            )

    conversation_id = await _ready_state(database, users[0])
    async with database() as session:
        with pytest.raises(StalePlanningState):
            await submit_for_review(
                session,
                conversation_id,
                users[0],
                agent,
                ReviewCommand(99, 1, "stale"),
                gateway,
            )
        session.add(
            MetabasePlanningOperation(
                conversation_id=conversation_id,
                operation_type="review_create",
                idempotency_key="uncertain",
                requirements_revision=0,
                plan_revision=1,
                status="outcome_unknown",
            )
        )
        await session.commit()
    async with database() as session:
        with pytest.raises(PlanningConflict, match="reconciliation"):
            await submit_for_review(
                session,
                conversation_id,
                users[0],
                agent,
                ReviewCommand(3, 1, "uncertain"),
                gateway,
            )


@pytest.mark.integration
async def test_unclassified_gateway_failure_is_recorded_as_unknown(database, users) -> None:
    """Convert unexpected adapter failures into a bounded non-repeatable outcome."""
    conversation_id = await _ready_state(database, users[0])

    class Gateway(FakeReviewGateway):
        """Raise an unclassified local adapter failure."""

        async def create_issue(self, summary: str, description: str) -> ReviewIssue:
            """Fail without a known no-write guarantee."""
            raise ValueError("internal details")

    async with database() as session:
        with pytest.raises(ReviewSubmissionUnavailable, match="unavailable"):
            await submit_for_review(
                session,
                conversation_id,
                users[0],
                SimpleNamespace(id="assistant"),
                ReviewCommand(3, 1, "unexpected"),
                Gateway(),
            )


@pytest.mark.integration
async def test_external_success_without_local_audit_state_fails_closed(database, users) -> None:
    """Refuse to report success if the durable aggregate disappeared concurrently."""
    conversation_id = await _ready_state(database, users[0])

    class DeletingGateway(FakeReviewGateway):
        """Delete the local aggregate before returning an external issue."""

        async def create_issue(self, summary: str, description: str) -> ReviewIssue:
            """Simulate a concurrent conversation deletion."""
            async with database() as other:
                conversation = await other.get(Conversation, conversation_id)
                await other.delete(conversation)
                await other.commit()
            return await super().create_issue(summary, description)

    async with database() as session:
        with pytest.raises(ReviewSubmissionUnavailable, match="audit state"):
            await submit_for_review(
                session,
                conversation_id,
                users[0],
                SimpleNamespace(id="assistant"),
                ReviewCommand(3, 1, "deleted"),
                DeletingGateway(),
            )
