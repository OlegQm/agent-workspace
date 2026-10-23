"""Characterize persisted workspace-access policy service behavior."""

import json
from pathlib import Path

import pytest
from sqlalchemy import select

from features.workspace.domain.exceptions import ProtectedWorkspaceMutation
from features.workspace.infrastructure.policies.service import WorkspacePolicyService
from infrastructure.database.models import WorkspacePathPolicy


@pytest.mark.integration
async def test_workspace_policy_persistence_and_policy_file(database, tmp_path: Path) -> None:
    """Preserve explicit, inherited, move, removal, and agent-visible policy behavior."""
    workspace = tmp_path / "agent" / "workspace"
    workspace.mkdir(parents=True)
    async with database() as session:
        service = WorkspacePolicyService(session, "assistant")
        await service.set_policy("private", True)
        assert await service.protected_paths() == ["private"]
        assert await service.is_protected("private/report.xlsx")
        with pytest.raises(ProtectedWorkspaceMutation, match="protected"):
            await service.require_mutable("private/report.xlsx")
        await service.require_mutable("public/report.xlsx")
        await service.move_policies("private", "restricted")
        assert await service.protected_paths() == ["restricted"]
        await service.write_policy_file(workspace)
        policy_file = workspace.parent / "workspace-access-policy.json"
        assert policy_file.stat().st_mode & 0o777 == 0o444
        assert json.loads(policy_file.read_text())["protected_paths"] == ["restricted"]
        await service.remove_policies("restricted")
        assert await service.protected_paths() == []
        await service.set_policy("private/report.xlsx", True)
        await service.set_policy("private/report.xlsx", True)
        await service.set_policy("private/report.xlsx", False)
        assert (await session.scalars(select(WorkspacePathPolicy))).all() == []


@pytest.mark.integration
async def test_workspace_policy_noop_move_and_remove_branches(database) -> None:
    """Preserve no-op commits when no policy matches a moved or removed path."""
    async with database() as session:
        service = WorkspacePolicyService(session, "assistant")
        await service.set_policy("private.xlsx", True)
        await service.move_policies("other", "renamed")
        assert await service.protected_paths() == ["private.xlsx"]
        await service.remove_policies("other")
        assert await service.protected_paths() == ["private.xlsx"]
        await service.set_policy("missing.xlsx", False)
        assert await service.protected_paths() == ["private.xlsx"]
