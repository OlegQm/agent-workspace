"""Provide MCP registration doubles shared by integration API tests."""

from collections.abc import Callable
from typing import Any


class ToolRegistry:
    """Collect functions registered through the FastMCP decorator API."""

    def __init__(self) -> None:
        """Initialize an empty tool registry."""
        self.tools: dict[str, Callable[..., Any]] = {}

    def tool(self, *_args: Any, **_kwargs: Any) -> Callable:
        """Return a decorator that records a tool by function name."""

        def register(function: Callable[..., Any]) -> Callable[..., Any]:
            """Record and return one tool function."""
            self.tools[function.__name__] = function
            return function

        return register


class AuditStub:
    """Preserve callable shape without writing audit records."""

    @staticmethod
    def audited(_name: str) -> Callable:
        """Return a transparent audit decorator."""

        def decorate(function: Callable[..., Any]) -> Callable[..., Any]:
            """Return the original function unchanged."""
            return function

        return decorate


class ServiceStub:
    """Expose arbitrary callable integration operations."""

    def __getattr__(self, _name: str) -> Callable[..., dict[str, bool]]:
        """Return a deterministic callable for any operation."""
        return lambda *_args, **_kwargs: {"ok": True}


def registered_tool_names(registrar: Callable[..., None]) -> set[str]:
    """Register one integration and return its public tool names."""
    registry = ToolRegistry()
    registrar(registry, ServiceStub(), AuditStub())
    return set(registry.tools)
