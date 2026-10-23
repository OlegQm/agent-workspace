"""Test the ClickUp MCP registration contract."""

from support.mcp import registered_tool_names

from tool_gateway.integrations.clickup.api.tools import register_tools


def test_register_tools_exposes_clickup_operations() -> None:
    """Register the exact ClickUp tool set."""
    assert registered_tool_names(register_tools) == {
        "clickup_list_spaces",
        "clickup_list_folders",
        "clickup_list_lists",
        "clickup_list_tasks",
        "clickup_get_task",
        "clickup_get_custom_fields",
        "clickup_list_attachments",
        "clickup_download_attachment",
    }
