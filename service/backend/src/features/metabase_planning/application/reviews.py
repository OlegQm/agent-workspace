"""Submit current structured plans to one durable external review issue."""

import re
import uuid
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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
from infrastructure.database.models import Conversation, User, utcnow

YOUTRACK_ISSUE_SUMMARY_PREFIX = "[AI GENERATED METABASE CHART PLAN]"
UNSAFE_REVIEW_REFERENCE = re.compile(
    r"(?:https?://|(?:^|\s)(?:/|\.\.?/|[A-Za-z]:\\)|\b(?:workspace|attachment)s?[/\\]|"
    r"\.(?:csv|docx?|pdf|xlsx?|json|sql|zip)\b)",
    re.IGNORECASE,
)


class ReviewSubmissionUnavailable(RuntimeError):
    """Signal that an external write has no safely repeatable known outcome."""


class ReviewSubmissionRejected(RuntimeError):
    """Signal that the external service definitively rejected a write."""


class ReviewIssueNotFound(ReviewSubmissionRejected):
    """Signal that YouTrack definitively confirmed a linked issue is missing."""


@dataclass(frozen=True)
class ReviewCommand:
    """Carry a confirmed current plan submission from the HTTP boundary."""

    workflow_version: int
    plan_revision: int
    idempotency_key: str


@dataclass(frozen=True)
class ReviewIssue:
    """Represent the bounded YouTrack fields persisted and shown to users."""

    id: str
    key: str
    status: str | None


class ReviewGateway(Protocol):
    """Define external review operations used by the application service."""

    async def create_issue(self, summary: str, description: str) -> ReviewIssue:
        """Create one review issue."""

    async def update_issue(self, issue_id: str, description: str, comment: str) -> ReviewIssue:
        """Replace one linked issue plan and append a revision note."""


class ReviewAgent(Protocol):
    """Expose the agent identity used to authorize an owned conversation."""

    id: str


def build_review_description(plan: StructuredPlan) -> str:
    """Serialize only validated business-plan statements for YouTrack."""
    plan.validate_for_submission()
    if any(UNSAFE_REVIEW_REFERENCE.search(statement.text) for statement in plan.statements()):
        raise ValueError("Review plan contains workspace or external references")
    sections: tuple[tuple[str, list], ...] = (
        ("Metrics and definitions", plan.metrics),
        ("Business sources", plan.sources),
        ("Period", plan.period),
        ("Grouping", plan.grain),
        ("Breakdowns", plan.dimensions),
        ("Filters", plan.filters),
        ("Comparisons", plan.comparisons),
        ("Exclusions", plan.exclusions),
        ("Proposed visualization", plan.visualization),
        ("Expected interpretation", plan.expected_interpretation),
        ("Assumptions and remaining ambiguity", plan.assumptions),
        ("Explicit answers", plan.explicit_answers),
    )
    lines = ["## Business question", "", plan.business_question.text]
    for heading, statements in sections:
        lines.extend(("", f"## {heading}", ""))
        lines.extend(f"- {statement.text}" for statement in statements)
        if not statements:
            lines.append("- None")
    return "\n".join(lines)


async def submit_for_review(
    session: AsyncSession,
    conversation_id: uuid.UUID,
    user: User,
    agent: ReviewAgent,
    command: ReviewCommand,
    gateway: ReviewGateway,
) -> MetabasePlanningState:
    """Create or update one linked issue with durable idempotency protection."""
    state = await session.scalar(
        select(MetabasePlanningState)
        .join(Conversation)
        .where(
            Conversation.id == conversation_id,
            Conversation.user_id == user.id,
            Conversation.agent_id == agent.id,
            Conversation.kind == "metabase_planning",
        )
        .with_for_update()
    )
    if state is None:
        raise PlanningConversationNotFound
    existing = await session.scalar(
        select(MetabasePlanningOperation).where(
            MetabasePlanningOperation.conversation_id == conversation_id,
            MetabasePlanningOperation.idempotency_key == command.idempotency_key,
        )
    )
    if existing is not None:
        if existing.status == "completed":
            return state
        if existing.status in {"pending", "outcome_unknown"}:
            raise PlanningConflict("Review submission outcome requires reconciliation")
    if (
        state.workflow_version != command.workflow_version
        or state.plan_revision != command.plan_revision
        or state.plan_for_requirements_revision != state.requirements_revision
        or state.structured_plan is None
        or state.workflow_state != "plan_ready"
        or state.last_submitted_plan_revision == state.plan_revision
    ):
        raise StalePlanningState("Plan changed; review the newest revision")

    plan = StructuredPlan.model_validate(state.structured_plan)
    description = build_review_description(plan)
    summary = f"{YOUTRACK_ISSUE_SUMMARY_PREFIX} {plan.business_question.text}"
    active_operation = await session.scalar(
        select(MetabasePlanningOperation).where(
            MetabasePlanningOperation.conversation_id == conversation_id,
            MetabasePlanningOperation.status.in_(("pending", "outcome_unknown")),
        )
    )
    if active_operation is not None:
        raise PlanningConflict("A review submission is already in progress")
    if existing is None:
        operation = MetabasePlanningOperation(
            conversation_id=conversation_id,
            operation_type="review_update" if state.youtrack_issue_id else "review_create",
            idempotency_key=command.idempotency_key,
            requirements_revision=state.requirements_revision,
            plan_revision=state.plan_revision,
            status="pending",
            attempt_count=1,
        )
        session.add(operation)
    else:
        operation = existing
        operation.status = "pending"
        operation.safe_error_code = None
        operation.finished_at = None
        operation.attempt_count += 1
        operation.updated_at = utcnow()
    issue_id = state.youtrack_issue_id
    await session.commit()
    try:
        if issue_id:
            try:
                issue = await gateway.update_issue(
                    issue_id,
                    description,
                    f"Plan revision {state.plan_revision} submitted from the planning conversation.",
                )
            except ReviewIssueNotFound:
                operation.operation_type = "review_recreate"
                operation.updated_at = utcnow()
                state.youtrack_issue_id = None
                state.youtrack_issue_key = None
                state.issue_status = None
                state.issue_status_checked_at = None
                state.issue_status_refresh_error = None
                state.updated_at = utcnow()
                await session.commit()
                issue = await gateway.create_issue(summary, description)
        else:
            issue = await gateway.create_issue(summary, description)
    except ReviewSubmissionRejected:
        operation.status = "failed"
        operation.safe_error_code = "review_rejected"
        operation.finished_at = utcnow()
        operation.updated_at = utcnow()
        await session.commit()
        raise
    except Exception as exc:
        operation.status = "outcome_unknown"
        operation.safe_error_code = "review_unavailable"
        operation.finished_at = utcnow()
        operation.updated_at = utcnow()
        await session.commit()
        if isinstance(exc, ReviewSubmissionUnavailable):
            raise
        raise ReviewSubmissionUnavailable("Review service unavailable") from exc

    state = await session.scalar(
        select(MetabasePlanningState)
        .where(MetabasePlanningState.conversation_id == conversation_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    operation = await session.scalar(
        select(MetabasePlanningOperation)
        .where(MetabasePlanningOperation.id == operation.id)
        .with_for_update()
    )
    if state is None or operation is None:
        raise ReviewSubmissionUnavailable("Review audit state is unavailable")
    now = utcnow()
    state.youtrack_issue_id = issue.id
    state.youtrack_issue_key = issue.key
    state.last_submitted_plan_revision = operation.plan_revision
    state.last_submitted_at = now
    state.issue_status = issue.status
    state.issue_status_checked_at = now
    state.issue_status_refresh_error = None
    if (
        state.requirements_revision == operation.requirements_revision
        and state.plan_revision == operation.plan_revision
        and state.workflow_state == "plan_ready"
    ):
        state.workflow_state = "submitted"
        state.workflow_version += 1
    state.updated_at = now
    operation.status = "completed"
    operation.finished_at = now
    operation.updated_at = now
    await session.commit()
    return state
