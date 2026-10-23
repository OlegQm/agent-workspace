"""Test application startup lifecycle orchestration."""

from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
from fastapi import FastAPI

from bootstrap import lifecycle


@pytest.mark.unit
async def test_lifespan_prepares_agents_database_policies_and_runs(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Run startup operations in their established order with injected dependencies."""
    calls: list[tuple] = []
    workspace = tmp_path / "assistant" / "workspace"
    agent = SimpleNamespace(id="assistant", workspace_root=workspace)

    class Initializer:
        """Record database initialization."""

        async def initialize(self) -> None:
            """Record initialization invocation."""
            calls.append(("database",))

    @asynccontextmanager
    async def session_factory():
        """Yield an injected session boundary."""
        session = object()
        calls.append(("session", session))
        yield session

    async def write_policy(session: object, agent_id: str, root) -> None:
        """Record policy-file generation."""
        calls.append(("policy", session, agent_id, root))

    async def recover() -> None:
        """Record interrupted-run recovery."""
        calls.append(("recover",))

    monkeypatch.setattr(lifecycle, "write_agent_policy_file", write_policy)
    monkeypatch.setattr(lifecycle, "recover_interrupted_runs", recover)
    application = FastAPI()
    application.state.container = SimpleNamespace(
        settings=SimpleNamespace(preview_cache_dir=tmp_path / "preview-cache"),
        agent_loader=lambda: {"assistant": agent},
        database_initializer=Initializer(),
        session_factory=session_factory,
    )

    async with lifecycle.lifespan(application):
        assert workspace.is_dir()
        assert (workspace / "outputs").is_dir()
        assert (tmp_path / "preview-cache").is_dir()

    assert calls[0] == ("database",)
    assert calls[-1] == ("recover",)
    assert any(call[0] == "policy" and call[2:] == ("assistant", workspace) for call in calls)
