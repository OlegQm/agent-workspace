"""Test validated planner results entering authoritative workflow state."""

import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from features.metabase_planning.application.results import apply_planner_result
from features.metabase_planning.infrastructure.hermes.contracts import PlannerResult
from features.metabase_planning.infrastructure.persistence.models import MetabasePlanningState
from infrastructure.database.models import Conversation, Message, User


def _payload(*, exact: bool = False, collection_id: int = 53, plan: dict | None = None) -> dict:
    """Build a machine planner result for one test turn."""
    candidate = None
    if exact:
        candidate = {
            "question_id": 42,
            "collection_id": collection_id,
            "title": "Paid revenue",
            "summary": "Monthly paid revenue",
            "metabase_verified": True,
            "metric_aligned": True,
            "filters_aligned": True,
            "time_aligned": True,
            "grain_aligned": True,
            "visualization_aligned": True,
            "intent_aligned": True,
            "ambiguities": [],
        }
    return {
        "assistant_message": "Here is the current result.",
        "signature": {
            "business_intent": "Track revenue",
            "metric_definition": "Paid revenue",
            "source": "Stripe",
            "population_filter": "All payments",
            "period_comparison": "This year",
            "granularity": "Month",
            "visualization": "Line chart",
        },
        "discovery": {
            "status": "exact_match" if exact else "no_match",
            "candidate": candidate,
        },
        "plan": plan,
    }


async def _planning_state(database, users: tuple[User, User]) -> MetabasePlanningState:
    """Create one planning aggregate in disposable PostgreSQL."""
    async with database() as session:
        conversation = Conversation(
            user_id=users[0].id,
            agent_id="assistant",
            title="Revenue",
            kind="metabase_planning",
        )
        session.add(conversation)
        await session.flush()
        state = MetabasePlanningState(conversation_id=conversation.id)
        session.add(state)
        await session.commit()
        await session.refresh(state)
        return state


@pytest.mark.integration
async def test_authorized_exact_match_becomes_a_server_candidate(database, users) -> None:
    """Publish exact-match actions only inside the agent's collection scope."""
    state = await _planning_state(database, users)
    agent = SimpleNamespace(resources=SimpleNamespace(metabase_collection_ids=[53]))

    async with database() as session:
        await apply_planner_result(
            session,
            state.conversation_id,
            PlannerResult.model_validate(_payload(exact=True)),
            agent,
            expected_requirements_revision=0,
        )

    async with database() as session:
        stored = await session.get(MetabasePlanningState, state.conversation_id)
        message = await session.scalar(
            select(Message).where(Message.conversation_id == state.conversation_id)
        )
        assert stored.workflow_state == "match_proposed"
        assert stored.candidate_question_id == 42
        assert stored.candidate_collection_id == 53
        assert message.content == "Here is the current result."


@pytest.mark.integration
async def test_out_of_scope_candidate_fails_closed(database, users) -> None:
    """Never disclose a Metabase Question outside the server-authorized scope."""
    state = await _planning_state(database, users)
    agent = SimpleNamespace(resources=SimpleNamespace(metabase_collection_ids=[53]))

    async with database() as session:
        with pytest.raises(ValueError, match="authorized Metabase scope"):
            await apply_planner_result(
                session,
                state.conversation_id,
                PlannerResult.model_validate(_payload(exact=True, collection_id=999)),
                agent,
                expected_requirements_revision=0,
            )


@pytest.mark.integration
async def test_complete_plan_becomes_sendable_without_parsing_message_text(database, users) -> None:
    """Drive Send for review from validated plan state rather than assistant prose."""
    state = await _planning_state(database, users)
    agent = SimpleNamespace(resources=SimpleNamespace(metabase_collection_ids=[53]))
    statement = {"text": "Confirmed value", "provenance": "user_confirmed"}
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
        await apply_planner_result(
            session,
            state.conversation_id,
            PlannerResult.model_validate(_payload(plan=plan)),
            agent,
            expected_requirements_revision=0,
        )

    async with database() as session:
        stored = await session.get(MetabasePlanningState, state.conversation_id)
        assert stored.workflow_state == "plan_ready"
        assert stored.plan_revision == 1
        assert stored.structured_plan == plan


@pytest.mark.integration
async def test_backend_accepts_the_agents_discovery_decision(database, users) -> None:
    """Persist discovery outcomes without independently interpreting requirements."""
    state = await _planning_state(database, users)
    agent = SimpleNamespace(resources=SimpleNamespace(metabase_collection_ids=[53]))
    first_payload = _payload()
    first_payload["discovery"] = {"status": "not_required", "candidate": None}
    first = PlannerResult.model_validate(first_payload)
    async with database() as session:
        await apply_planner_result(
            session,
            state.conversation_id,
            first,
            agent,
            expected_requirements_revision=0,
        )

    changed_payload = _payload()
    changed_payload["signature"]["granularity"] = "Week"
    changed_payload["discovery"] = {"status": "not_required", "candidate": None}
    changed = PlannerResult.model_validate(changed_payload)
    async with database() as session:
        await apply_planner_result(
            session,
            state.conversation_id,
            changed,
            agent,
            expected_requirements_revision=0,
        )

    async with database() as session:
        stored = await session.get(MetabasePlanningState, state.conversation_id)
        assert stored.discovery_status == "not_required"
        assert stored.discovery_signature["granularity"] == "Week"


@pytest.mark.integration
async def test_planner_result_rejects_missing_state_and_stale_revision(database, users) -> None:
    """Fail closed before applying output to an absent or newer planning aggregate."""
    agent = SimpleNamespace(resources=SimpleNamespace(metabase_collection_ids=[53]))
    async with database() as session:
        with pytest.raises(RuntimeError, match="unavailable"):
            await apply_planner_result(
                session,
                uuid.uuid4(),
                PlannerResult.model_validate(_payload()),
                agent,
                expected_requirements_revision=0,
            )

    state = await _planning_state(database, users)
    async with database() as session:
        with pytest.raises(ValueError, match="stale"):
            await apply_planner_result(
                session,
                state.conversation_id,
                PlannerResult.model_validate(_payload()),
                agent,
                expected_requirements_revision=1,
            )


@pytest.mark.integration
async def test_unchanged_requirements_may_be_rediscovered_by_the_agent(database, users) -> None:
    """Allow the agent to repeat discovery without a backend signature veto."""
    state = await _planning_state(database, users)
    agent = SimpleNamespace(resources=SimpleNamespace(metabase_collection_ids=[53]))
    first = PlannerResult.model_validate(_payload())
    async with database() as session:
        await apply_planner_result(
            session,
            state.conversation_id,
            first,
            agent,
            expected_requirements_revision=0,
        )

    repeated = PlannerResult.model_validate(_payload())
    async with database() as session:
        await apply_planner_result(
            session,
            state.conversation_id,
            repeated,
            agent,
            expected_requirements_revision=0,
        )


@pytest.mark.unit
async def test_result_can_finish_when_parent_conversation_disappeared() -> None:
    """Keep structured-state persistence bounded during a concurrent parent deletion."""
    state = MetabasePlanningState(
        conversation_id=uuid.uuid4(),
        requirements_revision=0,
        workflow_version=0,
        plan_revision=0,
    )

    class Session:
        """Return planner state but no parent conversation."""

        async def scalar(self, _statement):
            """Return the isolated planning state."""
            return state

        async def get(self, _model, _identifier):
            """Represent the concurrently deleted conversation."""
            return

        def add(self, _value) -> None:
            """Accept the user-facing message for this defensive branch."""

        async def commit(self) -> None:
            """Accept the bounded transaction."""

    await apply_planner_result(
        Session(),  # type: ignore[arg-type]
        state.conversation_id,
        PlannerResult.model_validate(_payload()),
        SimpleNamespace(resources=SimpleNamespace(metabase_collection_ids=[53])),
        expected_requirements_revision=0,
    )
