"""Present authoritative Metabase planning state to regular users and administrators."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from features.metabase_planning.infrastructure.persistence.models import (
    MetabasePlanningOperation,
    MetabasePlanningState,
)


def _action(visible: bool, enabled: bool, **extra: str | None) -> dict:
    """Build one explicit action descriptor without frontend inference."""
    return {
        "visible": visible,
        "enabled": enabled,
        "disabled_reason": None if enabled else ("operation_in_progress" if visible else None),
        **extra,
    }


def serialize_planning_state(
    record: MetabasePlanningState,
    operation: MetabasePlanningOperation | None = None,
    *,
    administrator: bool = False,
) -> dict:
    """Serialize persisted state and derive every allowed UI action server-side."""
    busy = operation is not None and operation.status in {"pending", "outcome_unknown"}
    candidate_current = (
        record.workflow_state == "match_proposed"
        and record.candidate_question_id is not None
        and record.candidate_for_revision == record.requirements_revision
    )
    plan_current = (
        record.workflow_state == "plan_ready"
        and record.structured_plan is not None
        and record.plan_for_requirements_revision == record.requirements_revision
        and record.last_submitted_plan_revision != record.plan_revision
    )
    can_interact = not administrator
    review_mode = "update" if record.youtrack_issue_id else "create"
    candidate_visible = candidate_current and can_interact
    open_visible = record.workflow_state == "resolved_existing" and can_interact
    review_visible = plan_current and can_interact
    refresh_visible = record.youtrack_issue_id is not None and can_interact
    actions = {
        "accept_match": _action(candidate_visible, candidate_visible and not busy),
        "reject_match": _action(candidate_visible, candidate_visible and not busy),
        "open_metabase": _action(
            open_visible,
            open_visible and not busy,
        ),
        "send_for_review": _action(
            review_visible,
            review_visible and not busy,
            mode=review_mode if review_visible else None,
        ),
        "refresh_status": _action(
            refresh_visible,
            refresh_visible and not busy,
        ),
    }
    return {
        "state": record.workflow_state,
        "requirements_revision": record.requirements_revision,
        "workflow_version": record.workflow_version,
        "discovery_status": record.discovery_status,
        "operation": (
            {
                "id": str(operation.id),
                "type": operation.operation_type,
                "status": operation.status,
                "safe_error_code": operation.safe_error_code,
            }
            if operation is not None
            else None
        ),
        "candidate": (
            {
                "question_id": record.candidate_question_id,
                "title": record.candidate_title,
                "summary": record.candidate_summary,
            }
            if candidate_current
            else None
        ),
        "plan": (
            {
                "revision": record.plan_revision,
                "is_current": record.plan_for_requirements_revision
                == record.requirements_revision,
                "content": record.structured_plan,
            }
            if record.structured_plan is not None
            else None
        ),
        "review": {
            "issue_key": record.youtrack_issue_key,
            "status": record.issue_status,
            "last_submitted_revision": record.last_submitted_plan_revision,
            "submitted_at": record.last_submitted_at,
            "status_checked_at": record.issue_status_checked_at,
            "status_refresh_error": record.issue_status_refresh_error,
        },
        "actions": actions,
    }


async def planning_snapshot(
    session: AsyncSession,
    conversation_id,
    *,
    administrator: bool = False,
) -> dict | None:
    """Load the current planning state and most recent durable operation."""
    record = await session.get(MetabasePlanningState, conversation_id)
    if record is None:
        return None
    operation = await session.scalar(
        select(MetabasePlanningOperation)
        .where(MetabasePlanningOperation.conversation_id == conversation_id)
        .order_by(
            MetabasePlanningOperation.created_at.desc(),
            MetabasePlanningOperation.id.desc(),
        )
        .limit(1)
    )
    return serialize_planning_state(record, operation, administrator=administrator)
