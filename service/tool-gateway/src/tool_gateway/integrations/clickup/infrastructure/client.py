"""Provide the read-only ClickUp adapter."""

from collections.abc import Callable
from typing import Any

from tool_gateway.infrastructure.configuration.settings import Settings
from tool_gateway.infrastructure.exports.paths import ExportPathResolver
from tool_gateway.infrastructure.http.client import secure_http_client
from tool_gateway.infrastructure.http.limits import ResultLimiter
from tool_gateway.infrastructure.security.credentials import require_config
from tool_gateway.infrastructure.security.resources import require_allowed_exact
from tool_gateway.infrastructure.security.urls import require_https_url


class ClickUpClient:
    """Provide read-only operations for ClickUp."""

    def __init__(
        self,
        settings: Settings,
        paths: ExportPathResolver | None = None,
        limiter: ResultLimiter | None = None,
        http_client: Callable[..., Any] | None = None,
    ) -> None:
        """Initialize the client with its role-scoped configuration."""
        self.settings = settings
        self.paths = paths or ExportPathResolver(settings)
        self.limiter = limiter or ResultLimiter(settings)
        self.http_client = http_client

    def _profile(self, workspace_id: str) -> dict:
        """Handle internal profile details."""
        require_allowed_exact(
            workspace_id, self.settings.manifest.resources.clickup_workspaces, "ClickUp workspace"
        )
        return self.settings.credential("clickup", workspace_id)

    def _headers(self, workspace_id: str) -> dict[str, str]:
        """Handle internal headers details."""
        return {
            "Authorization": require_config(
                self._profile(workspace_id).get("token"), f"ClickUp {workspace_id} token"
            )
        }

    async def _get(self, workspace_id: str, path: str, params: Any = None) -> dict:
        """Return the requested data."""
        async with (self.http_client or secure_http_client)(timeout=30) as client:
            response = await client.get(
                f"https://api.clickup.com/api/v2/{path.lstrip('/')}",
                headers=self._headers(workspace_id),
                params=params,
            )
            response.raise_for_status()
            return response.json()

    async def list_spaces(self, workspace_id: str) -> dict:
        """List spaces."""
        data = await self._get(workspace_id, f"team/{workspace_id}/space", {"archived": "false"})
        allowed = set(self.settings.manifest.resources.clickup_spaces)
        data["spaces"] = [item for item in data.get("spaces", []) if str(item.get("id")) in allowed]
        return data

    async def list_folders(self, workspace_id: str, space_id: str) -> dict:
        """List folders."""
        require_allowed_exact(
            space_id, self.settings.manifest.resources.clickup_spaces, "ClickUp space"
        )
        return await self._get(workspace_id, f"space/{space_id}/folder", {"archived": "false"})

    async def list_lists(self, workspace_id: str, parent_type: str, parent_id: str) -> dict:
        """List lists."""
        if parent_type not in {"folder", "space"}:
            raise ValueError("ClickUp parent_type must be folder or space")
        if parent_type == "space":
            require_allowed_exact(
                parent_id, self.settings.manifest.resources.clickup_spaces, "ClickUp space"
            )
        data = await self._get(
            workspace_id, f"{parent_type}/{parent_id}/list", {"archived": "false"}
        )
        allowed = set(self.settings.manifest.resources.clickup_lists)
        data["lists"] = [item for item in data.get("lists", []) if str(item.get("id")) in allowed]
        return data

    async def list_tasks(
        self,
        workspace_id: str,
        list_id: str,
        page: int = 0,
        include_closed: bool = True,
        subtasks: bool = True,
        statuses: list[str] | None = None,
    ) -> dict:
        """List tasks."""
        require_allowed_exact(
            list_id, self.settings.manifest.resources.clickup_lists, "ClickUp list"
        )
        params: list[tuple[str, object]] = [
            ("page", max(page, 0)),
            ("include_closed", str(include_closed).lower()),
            ("subtasks", str(subtasks).lower()),
            ("include_markdown_description", "true"),
        ]
        params.extend(("statuses[]", status) for status in statuses or [])
        data = await self._get(workspace_id, f"list/{list_id}/task", params)
        return self.limiter.limit(data.get("tasks", []))

    async def get_task(self, workspace_id: str, task_id: str) -> dict:
        """Return task."""
        data = await self._get(
            workspace_id, f"task/{task_id}", {"include_markdown_description": "true"}
        )
        list_id = str(data.get("list", {}).get("id", ""))
        if list_id not in self.settings.manifest.resources.clickup_lists:
            raise ValueError("ClickUp task is outside allowlisted lists")
        return data

    async def get_custom_fields(self, workspace_id: str, list_id: str) -> dict:
        """Return custom fields."""
        require_allowed_exact(
            list_id, self.settings.manifest.resources.clickup_lists, "ClickUp list"
        )
        return await self._get(workspace_id, f"list/{list_id}/field")

    async def list_attachments(self, workspace_id: str, task_id: str) -> dict:
        """List attachments."""
        task = await self.get_task(workspace_id, task_id)
        rows = task.get("attachments", [])
        return self.limiter.limit(rows)

    async def download_attachment(
        self, workspace_id: str, task_id: str, attachment_id: str, destination: str
    ) -> dict:
        """Download attachment."""
        task = await self.get_task(workspace_id, task_id)
        attachment = next(
            (item for item in task.get("attachments", []) if str(item.get("id")) == attachment_id),
            None,
        )
        if not attachment:
            raise ValueError("ClickUp attachment is not attached to the allowlisted task")
        path = self.paths.resolve(destination)
        attachment_url = require_https_url(
            str(attachment["url"]),
            allowed_hosts={"clickup.com", "clickupusercontent.com"},
            allow_subdomains=True,
            label="ClickUp attachment URL",
        )
        async with (
            (self.http_client or secure_http_client)(
                timeout=60,
                follow_redirects=True,
                allowed_redirect_hosts={"clickup.com", "clickupusercontent.com"},
                allow_redirect_subdomains=True,
            ) as client,
            client.stream("GET", attachment_url, headers=self._headers(workspace_id)) as response,
        ):
            response.raise_for_status()
            size = await self.limiter.write_stream(
                response, path, self.settings.export_max_bytes("clickup")
            )
        return {"path": str(path.relative_to(self.settings.workspace)), "size": size}
