"""Expose policy operations for endpoint and lifecycle adapters."""

from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from features.workspace.infrastructure.policies.service import WorkspacePolicyService


async def protected_paths(session: AsyncSession, agent_id: str) -> list[str]:
    """Return all explicitly protected paths for an agent workspace."""
    return await WorkspacePolicyService(session, agent_id).protected_paths()


async def is_path_protected(session: AsyncSession, agent_id: str, path: str) -> bool:
    """Check inherited protection for a workspace path."""
    return await WorkspacePolicyService(session, agent_id).is_protected(path)


async def require_user_mutable_path(
    session: AsyncSession,
    agent_id: str,
    path: str,
    *,
    include_parent: bool = False,
) -> None:
    """Reject a regular-user mutation that touches a protected path."""
    await WorkspacePolicyService(session, agent_id).require_mutable(
        path, include_parent=include_parent
    )


async def set_path_policy(
    session: AsyncSession, agent_id: str, path: str, no_user_access: bool
) -> None:
    """Create or remove an explicit protected-path policy."""
    await WorkspacePolicyService(session, agent_id).set_policy(path, no_user_access)


async def move_path_policies(
    session: AsyncSession, agent_id: str, source: str, destination: str
) -> None:
    """Move policies attached to a renamed path and all descendants."""
    await WorkspacePolicyService(session, agent_id).move_policies(source, destination)


async def remove_path_policies(session: AsyncSession, agent_id: str, path: str) -> None:
    """Remove policies attached to a deleted path and its descendants."""
    await WorkspacePolicyService(session, agent_id).remove_policies(path)


async def write_agent_policy_file(
    session: AsyncSession, agent_id: str, workspace_root: Path
) -> None:
    """Write the agent-readable confidentiality policy outside the user workspace."""
    await WorkspacePolicyService(session, agent_id).write_policy_file(workspace_root)
