"""Test bounded planning route helpers and disabled integration states."""

import uuid

import httpx
import pytest
from fastapi import BackgroundTasks, HTTPException
from pydantic import SecretStr

from features.metabase_planning.api import router
from features.metabase_planning.api.schemas import (
    MatchDecisionBody,
    PlanningCorrectionBody,
    PlanningRunBody,
    ReviewBody,
)
from features.metabase_planning.application.reviews import (
    ReviewSubmissionRejected,
    ReviewSubmissionUnavailable,
)
from features.metabase_planning.domain.exceptions import (
    InvalidPlanningAttachment,
    PlanningConflict,
    PlanningConversationNotFound,
    StalePlanningState,
)
from tests.support.llm import configured_llm_profile


@pytest.mark.unit
def test_application_errors_are_translated_without_internal_details() -> None:
    """Map each expected application failure to a stable public status."""
    cases = (
        (PlanningConversationNotFound(), 404),
        (StalePlanningState("stale"), 409),
        (PlanningConflict(), 409),
        (InvalidPlanningAttachment("bad file"), 400),
        (PermissionError("secret"), 403),
        (ReviewSubmissionRejected("secret"), 503),
        (ReviewSubmissionUnavailable("secret"), 503),
        (RuntimeError("secret"), 500),
    )
    for error, expected in cases:
        translated = router._translate_error(error)
        assert translated.status_code == expected
        if expected >= 500:
            assert "secret" not in translated.detail


@pytest.mark.unit
async def test_runtime_capability_failure_becomes_service_unavailable(monkeypatch) -> None:
    """Fail closed when the standard Hermes session API is unavailable."""
    async def unavailable(_: str) -> None:
        """Raise one bounded runtime error."""
        raise RuntimeError("Agent runtime is unavailable")

    monkeypatch.setattr(router, "ensure_hermes_session_capability", unavailable)
    with pytest.raises(Exception) as error:
        await router._ensure_runtime("assistant")
    assert error.value.status_code == 503


@pytest.mark.unit
async def test_review_gateway_requires_complete_configuration(monkeypatch) -> None:
    """Build a client only after every external identifier and secret is configured."""
    monkeypatch.setattr(router.settings, "metabase_planning_youtrack_enabled", False)
    async with httpx.AsyncClient() as client:
        with pytest.raises(RuntimeError, match="not configured"):
            router.review_gateway(client)

        monkeypatch.setattr(router.settings, "metabase_planning_youtrack_enabled", True)
        monkeypatch.setattr(router.settings, "youtrack_base_url", "https://tracker.example.test")
        monkeypatch.setattr(router.settings, "youtrack_token", SecretStr("hidden"))
        monkeypatch.setattr(router.settings, "youtrack_project_id", "0-1")
        monkeypatch.setattr(router.settings, "youtrack_assignee_id", "1-2")
        monkeypatch.setattr(router.settings, "youtrack_assignee_field_id", "3-4")
        assert router.review_gateway(client).project_id == "0-1"


@pytest.mark.unit
async def test_route_boundaries_translate_application_failures(monkeypatch) -> None:
    """Exercise every endpoint-specific catch without opening an external connection."""
    conversation_id = uuid.uuid4()
    user = type("User", (), {"agent_id": "assistant"})()
    agent = type("Agent", (), {"id": "assistant", "llm": configured_llm_profile()})()

    async def noop(*_args, **_kwargs) -> None:
        """Provide an awaitable runtime capability result."""

    async def invalid(*_args, **_kwargs):
        """Raise one translated application error."""
        raise InvalidPlanningAttachment("bad attachment")

    monkeypatch.setattr(router, "_ensure_runtime", noop)
    monkeypatch.setattr(router, "get_agent", lambda _: agent)
    monkeypatch.setattr(router, "planning_snapshot", noop)
    monkeypatch.setattr(router, "queue_initial_turn", invalid)
    monkeypatch.setattr(router, "queue_correction", invalid)
    monkeypatch.setattr(router, "accept_match", invalid)
    monkeypatch.setattr(router, "reject_match", invalid)
    monkeypatch.setattr(router, "accepted_question_id", invalid)
    monkeypatch.setattr(router, "submit_for_review", invalid)
    monkeypatch.setattr(router, "refresh_issue_status", invalid)
    monkeypatch.setattr(router, "linked_issue_key", invalid)
    monkeypatch.setattr(router, "review_gateway", lambda _: object())
    monkeypatch.setattr(router.settings, "metabase_planning_metabase_links_enabled", True)
    monkeypatch.setattr(router.settings, "metabase_public_url", "https://bi.example.test")
    monkeypatch.setattr(router.settings, "metabase_planning_youtrack_enabled", True)
    monkeypatch.setattr(router.settings, "youtrack_base_url", "https://tracker.example.test")
    monkeypatch.setattr(router.settings, "youtrack_token", SecretStr("hidden"))
    monkeypatch.setattr(router.settings, "youtrack_project_id", "0-1")
    monkeypatch.setattr(router.settings, "youtrack_assignee_id", "1-2")
    monkeypatch.setattr(router.settings, "youtrack_assignee_field_id", "3-4")

    calls = (
        router.start_planning_conversation(
            PlanningRunBody(content="Revenue"), BackgroundTasks(), user, object()
        ),
        router.continue_planning_conversation(
            conversation_id,
            PlanningCorrectionBody(content="Revenue", workflow_version=0),
            BackgroundTasks(),
            user,
            object(),
        ),
        router.accept_existing_question(
            conversation_id, MatchDecisionBody(workflow_version=0), user, object()
        ),
        router.reject_existing_question(
            conversation_id, MatchDecisionBody(workflow_version=0), user, object()
        ),
        router.open_existing_question(conversation_id, user, object()),
        router.send_for_review(
            conversation_id,
            ReviewBody(workflow_version=0, plan_revision=1, idempotency_key="test"),
            user,
            object(),
        ),
        router.refresh_review_status(conversation_id, user, object()),
        router.open_review_issue(conversation_id, user, object()),
    )
    for call in calls:
        with pytest.raises(HTTPException) as error:
            await call
        assert error.value.status_code == 400


@pytest.mark.unit
async def test_route_success_boundaries_schedule_and_build_server_redirects(monkeypatch) -> None:
    """Cover scheduling and URL construction from server-owned identifiers."""
    conversation_id = uuid.uuid4()
    conversation = type("Conversation", (), {"id": conversation_id})()
    run = type("Run", (), {"id": uuid.uuid4()})()
    user = type("User", (), {"agent_id": "assistant"})()
    agent = type("Agent", (), {"id": "assistant", "llm": configured_llm_profile()})()

    async def noop(*_args, **_kwargs) -> None:
        """Provide an awaitable no-op."""

    async def initial(*_args, **_kwargs):
        """Return one queued conversation and run."""
        return conversation, run

    async def correction(*_args, **_kwargs):
        """Return one queued correction run."""
        return run

    async def snapshot(*_args, **_kwargs):
        """Return one bounded authoritative snapshot."""
        return {"state": "collecting"}

    async def question(*_args, **_kwargs):
        """Return one server-authorized Question ID."""
        return 42

    async def issue(*_args, **_kwargs):
        """Return one server-stored issue key."""
        return "BI-7"

    monkeypatch.setattr(router, "_ensure_runtime", noop)
    monkeypatch.setattr(router, "get_agent", lambda _: agent)
    monkeypatch.setattr(router, "queue_initial_turn", initial)
    monkeypatch.setattr(router, "queue_correction", correction)
    monkeypatch.setattr(router, "planning_snapshot", snapshot)
    monkeypatch.setattr(router, "serialize_conversation", lambda _: {"id": str(conversation_id)})
    monkeypatch.setattr(router, "serialize_run", lambda _: {"id": str(run.id)})
    monkeypatch.setattr(router, "accepted_question_id", question)
    monkeypatch.setattr(router, "linked_issue_key", issue)
    monkeypatch.setattr(router.settings, "metabase_planning_metabase_links_enabled", True)
    monkeypatch.setattr(router.settings, "metabase_public_url", "https://bi.example.test/")
    monkeypatch.setattr(router.settings, "metabase_planning_youtrack_enabled", True)
    monkeypatch.setattr(router.settings, "youtrack_base_url", "https://tracker.example.test/")
    monkeypatch.setattr(router.settings, "youtrack_token", SecretStr("hidden"))
    monkeypatch.setattr(router.settings, "youtrack_project_id", "0-1")
    monkeypatch.setattr(router.settings, "youtrack_assignee_id", "1-2")
    monkeypatch.setattr(router.settings, "youtrack_assignee_field_id", "3-4")

    first_tasks = BackgroundTasks()
    first = await router.start_planning_conversation(
        PlanningRunBody(content="Revenue"), first_tasks, user, object()
    )
    correction_tasks = BackgroundTasks()
    continued = await router.continue_planning_conversation(
        conversation_id,
        PlanningCorrectionBody(content="Weekly", workflow_version=0),
        correction_tasks,
        user,
        object(),
    )
    metabase = await router.open_existing_question(conversation_id, user, object())
    review = await router.open_review_issue(conversation_id, user, object())

    assert first["run"]["id"] == continued["run"]["id"]
    assert len(first_tasks.tasks) == len(correction_tasks.tasks) == 1
    assert metabase.headers["location"] == "https://bi.example.test/question/42"
    assert review.headers["location"] == "https://tracker.example.test/issue/BI-7"
