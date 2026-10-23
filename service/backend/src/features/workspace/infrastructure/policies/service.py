"""Persist and enforce workspace access policies."""

import json
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from features.workspace.domain.exceptions import ProtectedWorkspaceMutation
from features.workspace.domain.policies.paths import (
    mutation_touches_protected_path,
    normalize_workspace_path,
    path_is_within,
)
from infrastructure.database.models import WorkspacePathPolicy, utcnow


@dataclass
class WorkspacePolicyService:
    """Manage access policies within one agent's persisted workspace scope."""

    session: AsyncSession
    agent_id: str

    async def protected_paths(self) -> list[str]:
        """Return all explicitly protected paths for this agent workspace."""
        rows = await self.session.scalars(
            select(WorkspacePathPolicy.path).where(
                WorkspacePathPolicy.agent_id == self.agent_id,
                WorkspacePathPolicy.no_user_access.is_(True),
            )
        )
        return sorted(rows.all())

    async def is_protected(self, path: str) -> bool:
        """Check inherited protection for a workspace path."""
        normalized = normalize_workspace_path(path)
        return any(
            path_is_within(normalized, protected) for protected in await self.protected_paths()
        )

    async def require_mutable(self, path: str, *, include_parent: bool = False) -> None:
        """Reject a regular-user mutation that touches a protected path."""
        protected = await self.protected_paths()
        if mutation_touches_protected_path(path, protected, include_parent=include_parent):
            raise ProtectedWorkspaceMutation("This destination is protected and cannot be changed")

    async def set_policy(self, path: str, no_user_access: bool) -> None:
        """Create or remove an explicit protected-path policy."""
        normalized = normalize_workspace_path(path)
        existing = await self.session.scalar(
            select(WorkspacePathPolicy).where(
                WorkspacePathPolicy.agent_id == self.agent_id,
                WorkspacePathPolicy.path == normalized,
            )
        )
        if no_user_access:
            if existing is None:
                self.session.add(WorkspacePathPolicy(agent_id=self.agent_id, path=normalized))
            else:
                existing.no_user_access = True
                existing.updated_at = utcnow()
        elif existing is not None:
            await self.session.delete(existing)
        await self.session.commit()

    async def move_policies(self, source: str, destination: str) -> None:
        """Move policies attached to a renamed path and all descendants."""
        source = normalize_workspace_path(source)
        destination = normalize_workspace_path(destination)
        rows = list(
            (
                await self.session.scalars(
                    select(WorkspacePathPolicy).where(WorkspacePathPolicy.agent_id == self.agent_id)
                )
            ).all()
        )
        changed = False
        for row in rows:
            if path_is_within(row.path, source):
                row.path = f"{destination}{row.path[len(source) :]}"
                row.updated_at = utcnow()
                changed = True
        if changed:
            await self.session.commit()

    async def remove_policies(self, path: str) -> None:
        """Remove policies attached to a deleted path and its descendants."""
        normalized = normalize_workspace_path(path)
        rows = list(
            (
                await self.session.scalars(
                    select(WorkspacePathPolicy).where(WorkspacePathPolicy.agent_id == self.agent_id)
                )
            ).all()
        )
        ids = [row.id for row in rows if path_is_within(row.path, normalized)]
        if ids:
            await self.session.execute(
                delete(WorkspacePathPolicy).where(WorkspacePathPolicy.id.in_(ids))
            )
            await self.session.commit()

    async def write_policy_file(self, workspace_root: Path) -> None:
        """Write the agent-readable confidentiality policy outside the workspace."""
        target = workspace_root.parent / "workspace-access-policy.json"
        payload = {
            "version": 1,
            "protected_paths": await self.protected_paths(),
            "instructions": (
                "Protected files are analysis-only inputs. Never copy, convert, archive, export, or "
                "create a downloadable derivative of them. Never provide a workspace download link, "
                "raw rows, full pages, encoded content, or a near-equivalent reconstruction. A "
                "response may contain only the minimum aggregate or conclusion and, when essential, "
                "a short excerpt of at most 25 words. Refuse copy, conversion, archive, export, "
                "download, and link requests before calling any tool. Never claim that a blocked file "
                "was created and never invent a link to it. Treat follow-up link requests as the same "
                "prohibited request. Do not use shell or Python file-copy operations to bypass this "
                "policy. Protection applies only to an exact listed relative path or descendants of a "
                "listed directory; do not restrict similarly named files, other report months, or "
                "files that merely share a template."
            ),
        }
        temporary = target.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
        temporary.replace(target)
        target.chmod(0o444)
