"""Test workspace policy application operations."""

from pathlib import Path

import pytest

from features.workspace.application.policies import operations


@pytest.mark.unit
async def test_policy_operations_delegate_to_scoped_service(monkeypatch: pytest.MonkeyPatch) -> None:
    """Delegate every application operation through the agent-scoped service."""
    calls: list[tuple] = []

    class FakeService:
        """Record application-to-infrastructure delegation."""

        def __init__(self, session: object, agent_id: str) -> None:
            """Record service construction inputs."""
            calls.append(("init", session, agent_id))

        async def protected_paths(self) -> list[str]:
            """Return a representative protected path."""
            calls.append(("protected_paths",))
            return ["private"]

        async def is_protected(self, path: str) -> bool:
            """Return a representative protection decision."""
            calls.append(("is_protected", path))
            return True

        async def require_mutable(self, path: str, *, include_parent: bool = False) -> None:
            """Record mutation validation inputs."""
            calls.append(("require_mutable", path, include_parent))

        async def set_policy(self, path: str, no_user_access: bool) -> None:
            """Record a policy update."""
            calls.append(("set_policy", path, no_user_access))

        async def move_policies(self, source: str, destination: str) -> None:
            """Record a policy move."""
            calls.append(("move_policies", source, destination))

        async def remove_policies(self, path: str) -> None:
            """Record policy removal."""
            calls.append(("remove_policies", path))

        async def write_policy_file(self, workspace_root: Path) -> None:
            """Record policy-file generation."""
            calls.append(("write_policy_file", workspace_root))

    monkeypatch.setattr(operations, "WorkspacePolicyService", FakeService)
    session = object()
    workspace = Path("/tmp/workspace")

    assert await operations.protected_paths(session, "assistant") == ["private"]
    assert await operations.is_path_protected(session, "assistant", "private") is True
    await operations.require_user_mutable_path(
        session,
        "assistant",
        "private/report.xlsx",
        include_parent=True,
    )
    await operations.set_path_policy(session, "assistant", "private", True)
    await operations.move_path_policies(session, "assistant", "private", "restricted")
    await operations.remove_path_policies(session, "assistant", "restricted")
    await operations.write_agent_policy_file(session, "assistant", workspace)

    assert ("require_mutable", "private/report.xlsx", True) in calls
    assert ("set_policy", "private", True) in calls
    assert ("move_policies", "private", "restricted") in calls
    assert ("remove_policies", "restricted") in calls
    assert ("write_policy_file", workspace) in calls
