"""Test the code MCP registration contract."""

from support.mcp import registered_tool_names

from tool_gateway.integrations.code.api.tools import register_tools


def test_register_tools_exposes_code_operations() -> None:
    """Register the exact code tool set."""
    assert registered_tool_names(register_tools) == {
        "code_list_repositories",
        "code_repo_status",
        "code_list_tree",
        "code_read_file",
        "code_search",
        "code_log",
        "code_show_commit",
        "code_blame",
        "code_diff",
    }
