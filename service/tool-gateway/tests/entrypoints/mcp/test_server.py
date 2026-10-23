"""Test MCP server composition and console startup."""

import pytest

from tool_gateway.entrypoints.mcp import server


def test_assistant_gateway_registers_configured_readonly_tools() -> None:
    """Verify that the assistant gateway registers configured readonly tools."""
    tools = server.mcp._tool_manager._tools
    names = set(tools)
    assert {
        "metabase_export_question",
        "bigquery_dry_run",
        "superfaktura_list_companies",
        "clickup_get_task",
        "code_read_file",
    }.issubset(names)
    assert {"gopay_get_payment", "stripe_get_object"}.issubset(names)
    assert "postgres_readonly_query" not in names
    assert all(tool.annotations.readOnlyHint is True for tool in tools.values())
    assert all(tool.annotations.destructiveHint is False for tool in tools.values())
    assert all(tool.annotations.idempotentHint is True for tool in tools.values())


def test_main_delegates_to_uvicorn(monkeypatch: pytest.MonkeyPatch) -> None:
    """Run Uvicorn with the configured loopback endpoint and hardened options."""
    calls: list[tuple] = []
    monkeypatch.setattr(server.uvicorn, "run", lambda *args, **kwargs: calls.append((args, kwargs)))
    server.main()
    assert calls == [
        (
            (server.app,),
            {
                "host": server.settings.gateway_host,
                "port": server.settings.gateway_port,
                "proxy_headers": False,
                "server_header": False,
            },
        )
    ]
