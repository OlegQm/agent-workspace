"""Register the source-code MCP contract."""

from mcp.server.fastmcp import FastMCP

from tool_gateway.infrastructure.observability.audit import AuditRecorder
from tool_gateway.integrations.code.application.service import CodeService


def register_tools(mcp: FastMCP, code: CodeService, audit: AuditRecorder) -> None:
    """Register all source-code tools on an MCP server."""

    @mcp.tool()
    @audit.audited("code_list_repositories")
    def code_list_repositories() -> list[dict]:
        """List synchronized repositories allowed for this agent."""
        return code.list_repositories()

    @mcp.tool()
    @audit.audited("code_repo_status")
    def code_repo_status(repository: str) -> dict:
        """Read repository synchronization status."""
        return code.status(repository)

    @mcp.tool()
    @audit.audited("code_list_tree")
    def code_list_tree(repository: str, path: str = "", revision: str | None = None) -> dict:
        """List a tree at an allowed commit."""
        return code.list_tree(repository, path, revision)

    @mcp.tool()
    @audit.audited("code_read_file")
    def code_read_file(repository: str, path: str, revision: str | None = None) -> dict:
        """Read a non-binary, non-secret source file."""
        return code.read_file(repository, path, revision)

    @mcp.tool()
    @audit.audited("code_search")
    def code_search(
        repository: str, query: str, path: str = "", revision: str | None = None
    ) -> dict:
        """Search text in an allowed repository."""
        return code.search(repository, query, path, revision)

    @mcp.tool()
    @audit.audited("code_log")
    def code_log(repository: str, limit: int = 50) -> dict:
        """Read default-branch history."""
        return code.log(repository, limit)

    @mcp.tool()
    @audit.audited("code_show_commit")
    def code_show_commit(repository: str, revision: str) -> dict:
        """Read commit metadata and file statistics."""
        return code.show_commit(repository, revision)

    @mcp.tool()
    @audit.audited("code_blame")
    def code_blame(repository: str, path: str, revision: str | None = None) -> dict:
        """Read blame data for a non-secret file."""
        return code.blame(repository, path, revision)

    @mcp.tool()
    @audit.audited("code_diff")
    def code_diff(repository: str, from_revision: str, to_revision: str) -> dict:
        """Read a redacted diff between allowed commits."""
        return code.diff(repository, from_revision, to_revision)
