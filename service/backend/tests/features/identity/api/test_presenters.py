"""Test HTTP serialization owned by the identity slice."""

from types import SimpleNamespace

import pytest

from features.identity.api import presenters
from infrastructure.database.models import User
from tests.support.llm import configured_llm_profile


def test_regular_and_administrator_user_serializers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify that identity responses expose only role-appropriate agent metadata."""
    monkeypatch.setattr(
        presenters,
        "get_agent",
        lambda _: SimpleNamespace(
            display_name="Assistant", tools=["metabase"], llm=configured_llm_profile()
        ),
    )
    regular = User(
        username="assistant-user",
        password_hash="unused",
        agent_id="assistant",
        locale="en",
    )
    administrator = User(
        username="administrator",
        password_hash="unused",
        locale="en",
        is_admin=True,
    )

    assert presenters.serialize_user(regular)["tools"] == ["metabase"]
    assert presenters.serialize_user(regular)["model_modes"] == [
        {"value": "small", "label": "Luna", "description": "GPT-5.6 Luna"},
        {"value": "medium", "label": "Terra", "description": "GPT-5.6 Terra"},
        {"value": "high", "label": "Sol", "description": "GPT-5.6 Sol"},
    ]
    assert presenters.serialize_user(regular)["default_model_mode"] == "medium"
    assert presenters.serialize_user(administrator)["agent_name"] == "Administration"
    assert presenters.serialize_admin_user(regular)["agent_name"] == "Assistant"


def test_identity_serializers_fail_closed_without_agent_assignment() -> None:
    """Verify that regular and managed-user serialization requires an assigned agent."""
    unassigned = User(username="unassigned", password_hash="unused")

    with pytest.raises(RuntimeError, match="no agent assignment"):
        presenters.serialize_user(unassigned)
    with pytest.raises(RuntimeError, match="no agent assignment"):
        presenters.serialize_admin_user(unassigned)
