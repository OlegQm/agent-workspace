"""Test Metabase planning HTTP authorization and lifecycle contracts."""

from types import SimpleNamespace

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import select
from support.application import login

from bootstrap import app as application
from features.metabase_planning.api import router as planning_api
from features.metabase_planning.application.reviews import ReviewIssue
from features.metabase_planning.infrastructure.persistence.models import MetabasePlanningState
from infrastructure.database.models import AgentRun, Conversation, User


@pytest.mark.integration
@pytest.mark.contract
async def test_regular_user_creates_marked_planning_chat_and_admin_is_denied(
    users: tuple[User, User], configured_agent: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Create planning state only for an authenticated regular agent user."""
    executed: list[object] = []

    async def execute(run_id) -> None:
        """Record the scheduled planning run without contacting Hermes."""
        executed.append(run_id)

    monkeypatch.setattr(planning_api, "get_agent", lambda _: configured_agent)
    monkeypatch.setattr(planning_api, "execute_planning_run", execute)
    monkeypatch.setattr(planning_api, "ensure_hermes_session_capability", lambda _: _noop())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application.app), base_url="http://localhost"
    ) as client:
        await login(client, "assistant-user")
        response = await client.post(
            "/api/metabase-planning/conversations/runs",
            json={"content": "Show monthly paid revenue", "attachments": []},
        )
        assert response.status_code == 202
        payload = response.json()
        assert payload["conversation"]["kind"] == "metabase_planning"
        assert payload["conversation"]["planning"]["state"] == "collecting"
        assert payload["run"]["status"] == "queued"
        detail = await client.get(f"/api/conversations/{payload['conversation']['id']}")
        assert detail.json()["planning"]["actions"]["send_for_review"]["visible"] is False

        await client.post("/api/auth/logout")
        await login(client, "administrator")
        denied = await client.post(
            "/api/metabase-planning/conversations/runs",
            json={"content": "Admin request"},
        )

    assert denied.status_code == 403
    assert len(executed) == 1


@pytest.mark.integration
async def test_omitted_planning_mode_uses_agent_default(
    users: tuple[User, User], configured_agent: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Resolve a planning turn without an explicit mode through its agent profile."""
    configured_agent.llm = configured_agent.llm.model_copy(update={"default_mode": "high"})
    monkeypatch.setattr(planning_api, "get_agent", lambda _: configured_agent)
    monkeypatch.setattr(planning_api, "execute_planning_run", _noop_with_arg)
    monkeypatch.setattr(planning_api, "ensure_hermes_session_capability", _noop_with_arg)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application.app), base_url="http://localhost"
    ) as client:
        await login(client, "assistant-user")
        response = await client.post(
            "/api/metabase-planning/conversations/runs", json={"content": "Show revenue"}
        )

    assert response.status_code == 202
    assert response.json()["run"]["model_mode"] == "high"


async def _noop() -> None:
    """Provide an awaitable no-op for runtime capability tests."""


async def _noop_with_arg(_: object) -> None:
    """Provide an awaitable no-op for one-argument background tasks."""


@pytest.mark.integration
async def test_correction_uses_specialized_route_and_standard_route_rejects_planning_chat(
    users: tuple[User, User], configured_agent: SimpleNamespace, database, monkeypatch
) -> None:
    """Keep planner instructions and state transitions out of normal chat routes."""
    monkeypatch.setattr(planning_api, "get_agent", lambda _: configured_agent)
    monkeypatch.setattr(planning_api, "execute_planning_run", _noop_with_arg)
    monkeypatch.setattr(planning_api, "ensure_hermes_session_capability", _noop_with_arg)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application.app), base_url="http://localhost"
    ) as client:
        await login(client, "assistant-user")
        created = await client.post(
            "/api/metabase-planning/conversations/runs",
            json={"content": "Monthly revenue"},
        )
        conversation_id = created.json()["conversation"]["id"]
        async with database() as session:
            run = await session.scalar(
                select(AgentRun).where(AgentRun.conversation_id == conversation_id)
            )
            run.status = "completed"
            await session.commit()

        standard = await client.post(
            f"/api/conversations/{conversation_id}/runs",
            json={"content": "Weekly instead"},
        )
        corrected = await client.post(
            f"/api/metabase-planning/conversations/{conversation_id}/runs",
            json={"content": "Weekly instead", "workflow_version": 0},
        )
        stale = await client.post(
            f"/api/metabase-planning/conversations/{conversation_id}/runs",
            json={"content": "Stale tab", "workflow_version": 0},
        )

    assert standard.status_code == 409
    assert corrected.status_code == 202
    assert corrected.json()["planning"]["requirements_revision"] == 1
    assert stale.status_code == 409


@pytest.mark.integration
async def test_administrator_sees_planning_marker_without_actions(
    users: tuple[User, User], database
) -> None:
    """Expose planning history to administrators without invoking its workflow."""
    async with database() as session:
        conversation = Conversation(
            user_id=users[0].id,
            agent_id="assistant",
            title="Revenue chart",
            kind="metabase_planning",
        )
        session.add(conversation)
        await session.flush()
        session.add(
            MetabasePlanningState(
                conversation_id=conversation.id,
                workflow_state="plan_ready",
                plan_revision=1,
                plan_for_requirements_revision=0,
                structured_plan={"business_question": {"text": "Revenue"}},
            )
        )
        await session.commit()

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application.app), base_url="http://localhost"
    ) as client:
        await login(client, "administrator")
        response = await client.get(
            f"/api/admin/users/{users[0].id}/conversations/{conversation.id}"
        )

    assert response.status_code == 200
    assert response.json()["kind"] == "metabase_planning"
    assert all(
        action["visible"] is False
        for action in response.json()["planning"]["actions"].values()
    )


@pytest.mark.integration
async def test_match_actions_are_versioned_and_open_uses_a_server_redirect(
    users: tuple[User, User], configured_agent: SimpleNamespace, database, monkeypatch
) -> None:
    """Accept only a current candidate and keep the external URL off persisted state."""
    configured_agent.resources = SimpleNamespace(metabase_collection_ids=[53])
    async with database() as session:
        conversation = Conversation(
            user_id=users[0].id,
            agent_id="assistant",
            title="Revenue",
            kind="metabase_planning",
        )
        session.add(conversation)
        await session.flush()
        session.add(
            MetabasePlanningState(
                conversation_id=conversation.id,
                workflow_state="match_proposed",
                workflow_version=2,
                candidate_question_id=42,
                candidate_collection_id=53,
                candidate_title="Revenue",
                candidate_summary="Full match",
                candidate_for_revision=0,
            )
        )
        await session.commit()
        conversation_id = conversation.id

    monkeypatch.setattr(planning_api, "get_agent", lambda _: configured_agent)
    monkeypatch.setattr(planning_api.settings, "metabase_planning_metabase_links_enabled", True)
    monkeypatch.setattr(planning_api.settings, "metabase_public_url", "https://bi.example.test")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application.app),
        base_url="http://localhost",
        follow_redirects=False,
    ) as client:
        await login(client, "assistant-user")
        accepted = await client.post(
            f"/api/metabase-planning/conversations/{conversation_id}/match/accept",
            json={"workflow_version": 2},
        )
        stale = await client.post(
            f"/api/metabase-planning/conversations/{conversation_id}/match/accept",
            json={"workflow_version": 2},
        )
        opened = await client.get(
            f"/api/metabase-planning/conversations/{conversation_id}/open"
        )

    assert accepted.status_code == 200
    assert accepted.json()["state"] == "resolved_existing"
    assert stale.status_code == 409
    assert opened.status_code == 307
    assert opened.headers["location"] == "https://bi.example.test/question/42"


@pytest.mark.integration
async def test_review_submit_refresh_and_open_are_admin_denied_and_server_driven(
    users: tuple[User, User], configured_agent: SimpleNamespace, database, monkeypatch
) -> None:
    """Expose review actions only through configured authenticated server operations."""
    statement = {"text": "Monthly revenue", "provenance": "user_confirmed"}
    plan = {
        "business_question": statement,
        "metrics": [statement],
        "sources": [statement],
        "period": [statement],
        "grain": [statement],
        "dimensions": [],
        "filters": [],
        "comparisons": [],
        "exclusions": [],
        "visualization": [statement],
        "expected_interpretation": [],
        "assumptions": [],
        "explicit_answers": [],
    }
    async with database() as session:
        conversation = Conversation(
            user_id=users[0].id,
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
                workflow_version=4,
                plan_revision=1,
                plan_for_requirements_revision=0,
                structured_plan=plan,
            )
        )
        await session.commit()
        conversation_id = conversation.id

    class Gateway:
        """Provide local fake review operations."""

        async def create_issue(self, summary: str, description: str) -> ReviewIssue:
            """Return a fake linked issue."""
            return ReviewIssue(id="2-7", key="BI-7", status="Open")

        async def update_issue(self, issue_id: str, description: str, comment: str):
            """Reject unexpected update behavior in this test."""
            raise AssertionError

        async def fetch_status(self, issue_id: str) -> str:
            """Return one refreshed fake status."""
            return "In Progress"

    monkeypatch.setattr(planning_api, "get_agent", lambda _: configured_agent)
    monkeypatch.setattr(planning_api, "review_gateway", lambda _: Gateway())
    monkeypatch.setattr(planning_api.settings, "metabase_planning_youtrack_enabled", True)
    monkeypatch.setattr(planning_api.settings, "youtrack_base_url", "https://tracker.example.test")
    monkeypatch.setattr(planning_api.settings, "youtrack_token", SecretStr("hidden"))
    monkeypatch.setattr(planning_api.settings, "youtrack_project_id", "0-1")
    monkeypatch.setattr(planning_api.settings, "youtrack_assignee_id", "1-2")
    monkeypatch.setattr(planning_api.settings, "youtrack_assignee_field_id", "3-4")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application.app),
        base_url="http://localhost",
        follow_redirects=False,
    ) as client:
        await login(client, "assistant-user")
        submitted = await client.post(
            f"/api/metabase-planning/conversations/{conversation_id}/review",
            json={"workflow_version": 4, "plan_revision": 1, "idempotency_key": "tap-1"},
        )
        refreshed = await client.post(
            f"/api/metabase-planning/conversations/{conversation_id}/review/status"
        )
        opened = await client.get(
            f"/api/metabase-planning/conversations/{conversation_id}/review/open"
        )
        await client.post("/api/auth/logout")
        await login(client, "administrator")
        denied = await client.post(
            f"/api/metabase-planning/conversations/{conversation_id}/review/status"
        )

    assert submitted.status_code == 200
    assert submitted.json()["review"]["issue_key"] == "BI-7"
    assert refreshed.json()["review"]["status"] == "In Progress"
    assert opened.headers["location"] == "https://tracker.example.test/issue/BI-7"
    assert denied.status_code == 403


@pytest.mark.integration
async def test_external_actions_fail_closed_while_server_configuration_is_disabled(
    users: tuple[User, User], database, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Return bounded unavailable responses without constructing external clients."""
    monkeypatch.setattr(planning_api.settings, "metabase_planning_metabase_links_enabled", False)
    monkeypatch.setattr(planning_api.settings, "metabase_planning_youtrack_enabled", False)
    async with database() as session:
        conversation = Conversation(
            user_id=users[0].id,
            agent_id="assistant",
            title="Revenue",
            kind="metabase_planning",
        )
        session.add(conversation)
        await session.flush()
        session.add(MetabasePlanningState(conversation_id=conversation.id))
        await session.commit()

    base = f"/api/metabase-planning/conversations/{conversation.id}"
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application.app), base_url="http://localhost"
    ) as client:
        await login(client, "assistant-user")
        responses = [
            await client.get(f"{base}/open"),
            await client.post(
                f"{base}/review",
                json={"workflow_version": 0, "plan_revision": 1, "idempotency_key": "x"},
            ),
            await client.post(f"{base}/review/status"),
            await client.get(f"{base}/review/open"),
        ]

    assert [response.status_code for response in responses] == [503, 503, 503, 503]


@pytest.mark.integration
async def test_planning_routes_bound_invalid_and_stale_actions(
    users: tuple[User, User], configured_agent: SimpleNamespace, database, monkeypatch
) -> None:
    """Translate invalid attachments and unavailable current actions without details."""
    configured_agent.resources = SimpleNamespace(metabase_collection_ids=[53])
    async with database() as session:
        conversation = Conversation(
            user_id=users[0].id,
            agent_id="assistant",
            title="Revenue",
            kind="metabase_planning",
        )
        session.add(conversation)
        await session.flush()
        session.add(
            MetabasePlanningState(
                conversation_id=conversation.id,
                workflow_state="match_proposed",
                candidate_question_id=42,
                candidate_collection_id=53,
                candidate_title="Revenue",
                candidate_summary="Exact match",
                candidate_for_revision=0,
            )
        )
        await session.commit()

    monkeypatch.setattr(planning_api, "get_agent", lambda _: configured_agent)
    monkeypatch.setattr(planning_api, "ensure_hermes_session_capability", _noop_with_arg)
    monkeypatch.setattr(planning_api.settings, "metabase_planning_metabase_links_enabled", True)
    monkeypatch.setattr(planning_api.settings, "metabase_public_url", "https://bi.example.test")
    monkeypatch.setattr(planning_api.settings, "metabase_planning_youtrack_enabled", True)
    monkeypatch.setattr(planning_api.settings, "youtrack_base_url", "https://tracker.example.test")
    monkeypatch.setattr(planning_api.settings, "youtrack_token", SecretStr("hidden"))
    monkeypatch.setattr(planning_api.settings, "youtrack_project_id", "0-1")
    monkeypatch.setattr(planning_api.settings, "youtrack_assignee_id", "1-2")
    monkeypatch.setattr(planning_api.settings, "youtrack_assignee_field_id", "3-4")

    base = f"/api/metabase-planning/conversations/{conversation.id}"
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application.app), base_url="http://localhost"
    ) as client:
        await login(client, "assistant-user")
        invalid_start = await client.post(
            "/api/metabase-planning/conversations/runs",
            json={"content": "Revenue", "attachments": ["missing.xlsx"]},
        )
        rejected = await client.post(f"{base}/match/reject", json={"workflow_version": 0})
        stale_reject = await client.post(f"{base}/match/reject", json={"workflow_version": 0})
        unavailable_match = await client.get(f"{base}/open")
        stale_review = await client.post(
            f"{base}/review",
            json={"workflow_version": 1, "plan_revision": 1, "idempotency_key": "stale"},
        )
        missing_status = await client.post(f"{base}/review/status")
        missing_issue = await client.get(f"{base}/review/open")

    assert invalid_start.status_code == 400
    assert rejected.status_code == 200
    assert stale_reject.status_code == 409
    assert unavailable_match.status_code == 403
    assert stale_review.status_code == 409
    assert missing_status.status_code == 500
    assert missing_issue.status_code == 500
