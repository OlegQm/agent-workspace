"""Register the ClickUp MCP contract."""

from mcp.server.fastmcp import FastMCP

from tool_gateway.infrastructure.observability.audit import AuditRecorder
from tool_gateway.integrations.clickup.application.service import ClickUpService


def register_tools(mcp: FastMCP, clickup: ClickUpService, audit: AuditRecorder) -> None:
    """Register all ClickUp tools on an MCP server."""

    @mcp.tool()
    @audit.audited("clickup_list_spaces")
    async def clickup_list_spaces(workspace_id: str) -> dict:
        """List Spaces in an allowlisted Workspace."""
        return await clickup.list_spaces(workspace_id)

    @mcp.tool()
    @audit.audited("clickup_list_folders")
    async def clickup_list_folders(workspace_id: str, space_id: str) -> dict:
        """List folders in an allowlisted Workspace."""
        return await clickup.list_folders(workspace_id, space_id)

    @mcp.tool()
    @audit.audited("clickup_list_lists")
    async def clickup_list_lists(workspace_id: str, parent_type: str, parent_id: str) -> dict:
        """List configured Lists under a folder or Space."""
        return await clickup.list_lists(workspace_id, parent_type, parent_id)

    @mcp.tool()
    @audit.audited("clickup_list_tasks")
    async def clickup_list_tasks(
        workspace_id: str,
        list_id: str,
        page: int = 0,
        include_closed: bool = True,
        subtasks: bool = True,
        statuses: list[str] | None = None,
    ) -> dict:
        """Read one bounded task page from an allowlisted List."""
        return await clickup.list_tasks(
            workspace_id, list_id, page, include_closed, subtasks, statuses
        )

    @mcp.tool()
    @audit.audited("clickup_get_task")
    async def clickup_get_task(workspace_id: str, task_id: str) -> dict:
        """Read a task after validating List ownership."""
        return await clickup.get_task(workspace_id, task_id)

    @mcp.tool()
    @audit.audited("clickup_get_custom_fields")
    async def clickup_get_custom_fields(workspace_id: str, list_id: str) -> dict:
        """Read custom fields for an allowlisted List."""
        return await clickup.get_custom_fields(workspace_id, list_id)

    @mcp.tool()
    @audit.audited("clickup_list_attachments")
    async def clickup_list_attachments(workspace_id: str, task_id: str) -> dict:
        """List task attachments after List ownership validation."""
        return await clickup.list_attachments(workspace_id, task_id)

    @mcp.tool()
    @audit.audited("clickup_download_attachment")
    async def clickup_download_attachment(
        workspace_id: str, task_id: str, attachment_id: str, destination: str
    ) -> dict:
        """Download an allowlisted attachment into the workspace."""
        return await clickup.download_attachment(workspace_id, task_id, attachment_id, destination)
