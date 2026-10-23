"""Own application startup and shutdown side effects."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from features.chat.infrastructure.hermes.runtime import recover_interrupted_runs
from features.workspace.application.policies.operations import write_agent_policy_file
from features.workspace.infrastructure.previews.cache import ensure_cache_directory


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Handle lifespan."""
    container = _.state.container
    agents = container.agent_loader()
    ensure_cache_directory(container.settings.preview_cache_dir)
    for agent in agents.values():
        agent.workspace_root.mkdir(parents=True, exist_ok=True)
        (agent.workspace_root / "outputs").mkdir(exist_ok=True)
    await container.database_initializer.initialize()
    async with container.session_factory() as session:
        for agent in agents.values():
            await write_agent_policy_file(session, agent.id, agent.workspace_root)
    await recover_interrupted_runs()
    yield
