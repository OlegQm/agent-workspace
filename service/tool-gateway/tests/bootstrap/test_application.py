"""Characterize MCP composition, contracts, middleware, and CLI startup."""

import asyncio
import hashlib
import inspect
import json
from pathlib import Path
from typing import ClassVar

import pytest
from mcp.types import ToolAnnotations

from tool_gateway.bootstrap import application
from tool_gateway.bootstrap.container import ApplicationContainer
from tool_gateway.entrypoints.mcp import server
from tool_gateway.infrastructure.configuration.models import Manifest
from tool_gateway.infrastructure.configuration.settings import Settings
from tool_gateway.infrastructure.exports.paths import ExportPathResolver
from tool_gateway.infrastructure.exports.writer import TabularExporter
from tool_gateway.infrastructure.http.client import HttpClientFactory
from tool_gateway.infrastructure.http.limits import ResultLimiter
from tool_gateway.infrastructure.observability import audit

ASSISTANT_CONTRACT_HASH = "237e0c308cb4e4561f03552e7ddf0dde041401b961a62af979e28122bd8d82e9"
COMMON_TOOLS = {
    "metabase_search",
    "metabase_get_question",
    "metabase_get_dashboard",
    "metabase_run_question",
    "metabase_export_question",
    "metabase_readonly_query",
    "metabase_list_collections",
    "metabase_list_collection_items",
    "metabase_get_database_metadata",
    "metabase_get_table_metadata",
    "metabase_get_field_metadata",
    "metabase_list_dashboard_subscriptions",
    "metabase_get_collection_permissions",
    "metabase_get_safe_settings",
    "bigquery_list_datasets",
    "bigquery_get_dataset",
    "bigquery_list_tables",
    "bigquery_get_table",
    "bigquery_list_partitions",
    "bigquery_dry_run",
    "bigquery_readonly_query",
    "clickup_list_spaces",
    "clickup_list_folders",
    "clickup_list_lists",
    "clickup_list_tasks",
    "clickup_get_task",
    "clickup_get_custom_fields",
    "clickup_list_attachments",
    "clickup_download_attachment",
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
SUPERFAKTURA_TOOLS = {
    "superfaktura_list_companies",
    "superfaktura_list_invoices",
    "superfaktura_get_invoice",
    "superfaktura_get_invoice_payments",
    "superfaktura_list_clients",
    "superfaktura_get_client",
    "superfaktura_download_invoice_pdf",
}
ANALYTICS_TOOLS = {
    "google_ads_list_customers",
    "google_ads_get_customer",
    "google_ads_readonly_query",
    "google_ads_list_conversion_actions",
    "google_ads_get_change_history",
    "meta_ads_get_account",
    "meta_ads_list_objects",
    "meta_ads_account_activity",
    "meta_ads_insights",
    "google_analytics_run_report",
    "google_analytics_run_realtime_report",
    "google_analytics_get_metadata",
    "google_analytics_check_compatibility",
    "google_analytics_run_funnel_report",
    "google_analytics_admin_metadata",
}
PAYMENT_TOOLS = {
    "gopay_get_payment",
    "gopay_get_payments",
    "stripe_get_object",
    "stripe_list_objects",
}


class AwaitableResult(dict):
    """Act as a result for both synchronous and asynchronous adapter calls."""

    def __await__(self):
        """Return this mapping when awaited."""

        async def resolve() -> dict:
            """Resolve the stored mapping."""
            return self

        return resolve().__await__()


class AdapterStub:
    """Record arbitrary integration method calls."""

    calls: ClassVar[list[tuple[str, tuple, dict]]] = []

    def __getattr__(self, name: str):
        """Return a callable stub for any adapter operation."""

        def invoke(*args, **kwargs) -> AwaitableResult:
            """Record arguments and return a dual-mode result."""
            self.calls.append((name, args, kwargs))
            return AwaitableResult(method=name)

        return invoke


def load_manifest(name: str) -> Manifest:
    """Load a repository manifest through the production model."""
    import yaml

    path = Path(__file__).resolve().parents[4] / f"config/agents/{name}.yaml"
    return Manifest.model_validate(yaml.safe_load(path.read_text()))


def contract_hash(mcp) -> str:
    """Hash exact public tool names, descriptions, schemas, and annotations."""
    contract = {
        name: {
            "description": tool.description,
            "parameters": tool.parameters,
            "annotations": tool.annotations.model_dump(mode="json") if tool.annotations else None,
        }
        for name, tool in sorted(mcp._tool_manager._tools.items())
    }
    payload = json.dumps(contract, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def build_test_application(configuration: Settings, services: dict | None = None):
    """Build an MCP application with isolated integration service doubles."""
    recorder = audit.AuditRecorder(configuration)
    recorder.write = lambda _record: None  # type: ignore[method-assign]
    paths = ExportPathResolver(configuration)
    configured = (
        {name: AdapterStub() for name in configuration.manifest.tools}
        if services is None
        else services
    )
    return application.build_application(
        ApplicationContainer(
            settings=configuration,
            audit=recorder,
            paths=paths,
            exporter=TabularExporter(configuration, paths),
            limiter=ResultLimiter(configuration),
            http=HttpClientFactory(),
            services=configured,
        )
    )


def test_role_tool_contracts_are_exact(monkeypatch: pytest.MonkeyPatch) -> None:
    """Freeze the bundled assistant's complete public MCP contract."""
    manifest = load_manifest("assistant")
    monkeypatch.setattr(Settings, "manifest", property(lambda _self: manifest))
    configuration = server.settings
    monkeypatch.setattr(configuration, "gateway_role", "assistant")
    mcp = build_test_application(configuration)
    expected_names = COMMON_TOOLS | SUPERFAKTURA_TOOLS | ANALYTICS_TOOLS | PAYMENT_TOOLS
    assert set(mcp._tool_manager._tools) == expected_names
    assert contract_hash(mcp) == ASSISTANT_CONTRACT_HASH
    for tool in mcp._tool_manager._tools.values():
        assert tool.annotations == ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )


def test_all_tool_wrappers_delegate_every_argument(monkeypatch: pytest.MonkeyPatch) -> None:
    """Execute every optional integration wrapper against constructor-injected stubs."""
    manifest = load_manifest("assistant")
    manifest.id = "all"
    manifest.tools = [
        "metabase",
        "bigquery",
        "superfaktura",
        "gopay",
        "stripe",
        "google_ads",
        "meta_ads",
        "google_analytics",
        "clickup",
        "code",
    ]
    monkeypatch.setattr(Settings, "manifest", property(lambda _self: manifest))
    configuration = server.settings
    monkeypatch.setattr(configuration, "gateway_role", "all")
    AdapterStub.calls = []
    mcp = build_test_application(
        configuration,
        {name: AdapterStub() for name in manifest.tools},
    )
    assert len(mcp._tool_manager._tools) == 64

    async def run_tools() -> None:
        """Invoke every registered wrapper with all parameters populated."""
        for tool in mcp._tool_manager._tools.values():
            kwargs = {
                name: schema_value(schema)
                for name, schema in tool.parameters.get("properties", {}).items()
            }
            result = tool.fn(**kwargs)
            if inspect.isawaitable(result):
                result = await result
            assert result["method"]

        insight = mcp._tool_manager._tools["meta_ads_insights"]
        result = insight.fn(
            account_id="value",
            since="value",
            until="value",
            fields=["spend"],
        )
        if inspect.isawaitable(result):
            await result

    asyncio.run(run_tools())
    assert len(AdapterStub.calls) == 65


def schema_value(schema: dict):
    """Create one valid-shaped argument from a JSON schema property."""
    selected = schema
    if "anyOf" in schema:
        selected = next(item for item in schema["anyOf"] if item.get("type") != "null")
    return {
        "string": "value",
        "integer": 1,
        "boolean": True,
        "array": [],
    }.get(selected.get("type"), {})


def test_server_rejects_manifest_mismatches(monkeypatch: pytest.MonkeyPatch) -> None:
    """Characterize both role and environment startup checks."""
    manifest = load_manifest("assistant")
    monkeypatch.setattr(Settings, "manifest", property(lambda _self: manifest))
    configuration = server.settings
    monkeypatch.setattr(configuration, "gateway_role", "other")
    with pytest.raises(RuntimeError, match="role"):
        build_test_application(configuration)
    monkeypatch.setattr(configuration, "gateway_role", "assistant")
    manifest.resources.environment = "dev"
    with pytest.raises(RuntimeError, match="PROD"):
        build_test_application(configuration)


def test_server_can_register_an_empty_allowlisted_toolset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Characterize disabled branches for every optional integration."""
    manifest = load_manifest("assistant")
    manifest.tools = []
    monkeypatch.setattr(Settings, "manifest", property(lambda _self: manifest))
    configuration = server.settings
    monkeypatch.setattr(configuration, "gateway_role", "assistant")
    assert build_test_application(configuration)._tool_manager._tools == {}


def test_application_ignores_missing_and_unknown_integrations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Skip tools that have no service or no known registrar."""
    manifest = load_manifest("assistant")
    manifest.tools = ["metabase", "unknown"]
    monkeypatch.setattr(Settings, "manifest", property(lambda _self: manifest))
    configuration = server.settings
    monkeypatch.setattr(configuration, "gateway_role", "assistant")
    assert build_test_application(configuration, {"unknown": object()})._tool_manager._tools == {}
