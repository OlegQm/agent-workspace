"""Serialize identity records for HTTP responses."""

from features.agents.infrastructure.configuration.registry import get_agent
from infrastructure.database.models import User


def serialize_user(user: User) -> dict:
    """Serialize the authenticated user and permitted agent metadata."""
    if user.is_admin:
        return {
            "id": str(user.id),
            "username": user.username,
            "agent_id": None,
            "agent_name": "Administration",
            "locale": user.locale,
            "tools": [],
            "is_admin": True,
        }
    if not user.agent_id:
        raise RuntimeError("Regular user has no agent assignment")
    agent = get_agent(user.agent_id)
    return {
        "id": str(user.id),
        "username": user.username,
        "agent_id": user.agent_id,
        "agent_name": agent.display_name,
        "locale": user.locale,
        "tools": agent.tools,
        "model_modes": agent.llm.public_mode_descriptors(),
        "default_model_mode": agent.llm.default_mode,
        "is_admin": False,
    }


def serialize_admin_user(user: User) -> dict:
    """Serialize a regular user for an administrator workspace selector."""
    if not user.agent_id:
        raise RuntimeError("Managed user has no agent assignment")
    agent = get_agent(user.agent_id)
    return {
        "id": str(user.id),
        "username": user.username,
        "agent_id": user.agent_id,
        "agent_name": agent.display_name,
        "locale": user.locale,
        "is_active": user.is_active,
    }
