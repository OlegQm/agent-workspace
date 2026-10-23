"""Apply shared annotations to every MCP tool."""

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.server import Settings as FastMCPSettings
from mcp.types import ToolAnnotations

# MCP 1.26 leaves this model unresolved under Pydantic 2.12.
FastMCPSettings.model_rebuild()


class ReadOnlyFastMCP(FastMCP):
    """Apply the gateway's read-only contract to every registered tool."""

    def tool(self, *args, annotations=None, **kwargs):
        """Register a tool with read-only annotations unless explicitly supplied."""
        annotations = annotations or ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
        return super().tool(*args, annotations=annotations, **kwargs)
