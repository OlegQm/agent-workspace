"""Test default and explicit MCP tool annotations."""

from mcp.types import ToolAnnotations

from tool_gateway.entrypoints.mcp.annotations import ReadOnlyFastMCP


def test_tool_respects_explicit_annotations() -> None:
    """Preserve annotations explicitly supplied by a registrar."""
    mcp = ReadOnlyFastMCP("test")
    explicit = ToolAnnotations(readOnlyHint=False)

    @mcp.tool(annotations=explicit)
    def operation() -> None:
        """Provide a test operation."""

    assert mcp._tool_manager._tools["operation"].annotations == explicit
