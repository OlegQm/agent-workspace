"""Expose health endpoints for the API and authenticated agent runtime."""

import httpx
from fastapi import APIRouter, Depends

from features.agents.infrastructure.configuration.registry import get_agent
from features.chat.infrastructure.hermes.runtime import hermes_headers, hermes_runtime_compatible
from features.identity.api.dependencies import agent_user
from infrastructure.database.models import User

router = APIRouter()


@router.get("/healthz")
async def healthz():
    """Handle healthz."""
    return {"status": "ok"}


@router.get("/api/health")
async def health(user: User = Depends(agent_user)):
    """Handle health."""
    agent = get_agent(user.agent_id)
    hermes_status = "unavailable"
    try:
        async with httpx.AsyncClient(timeout=3, trust_env=False, follow_redirects=False) as client:
            response = await client.get(
                f"{str(agent.hermes_url).rstrip('/')}/v1/capabilities",
                headers=hermes_headers(agent.id),
            )
            if response.is_success:
                hermes_status = (
                    "ok" if hermes_runtime_compatible(response.json()) else "incompatible"
                )
            else:
                hermes_status = "error"
    except httpx.HTTPError:
        pass
    return {"status": "ok", "hermes": hermes_status}
