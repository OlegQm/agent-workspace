"""Characterize all Metabase operations without remote requests."""

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from tool_gateway.infrastructure.configuration.settings import Settings
from tool_gateway.integrations.metabase.infrastructure import client as module
from tool_gateway.integrations.metabase.infrastructure.client import MetabaseClient

settings = Settings()


class Response:
    """Provide a fake Metabase HTTP response."""

    def __init__(self, payload) -> None:
        """Store response JSON."""
        self.payload = payload

    def raise_for_status(self) -> None:
        """Represent success."""

    def json(self):
        """Return response JSON."""
        return self.payload


class Client:
    """Record fake Metabase GET and POST requests."""

    def __init__(self, payloads: list) -> None:
        """Store ordered response payloads."""
        self.payloads = payloads
        self.calls: list[tuple] = []

    async def __aenter__(self):
        """Enter the fake client."""
        return self

    async def __aexit__(self, *_args) -> None:
        """Exit the fake client."""

    async def get(self, url: str, **kwargs) -> Response:
        """Record GET and return the next response."""
        self.calls.append(("GET", url, kwargs))
        return Response(self.payloads.pop(0))

    async def post(self, url: str, **kwargs) -> Response:
        """Record POST and return the next response."""
        self.calls.append(("POST", url, kwargs))
        return Response(self.payloads.pop(0))


@pytest.fixture
def metabase_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> SimpleNamespace:
    """Configure deterministic Metabase resources and API-key authentication."""
    resources = SimpleNamespace(
        metabase_collection_ids=[1, 2],
        metabase_database_ids=[10],
        metabase_sql_tables=["public.orders"],
        metabase_sql_denied_columns=[],
        metabase_setting_keys=["site-name", "unsafe"],
        tool_export_limits={},
    )
    manifest = SimpleNamespace(resources=resources)
    monkeypatch.setattr(Settings, "manifest", property(lambda _self: manifest))
    monkeypatch.setattr(
        Settings,
        "optional_credential",
        lambda _self, source, alias="default": (
            {"url": "https://metabase.example.invalid/", "api_key": "key"} if source == "metabase" else {}
        ),
    )
    monkeypatch.setattr(settings, "agent_data_dir", tmp_path)
    monkeypatch.setattr(settings, "tool_result_max_rows", 1)
    return resources


def test_metabase_headers_and_generic_get(
    monkeypatch: pytest.MonkeyPatch,
    metabase_config: SimpleNamespace,
) -> None:
    """Characterize API-key headers, base URL normalization, and generic GET."""
    adapter = MetabaseClient(settings)
    assert adapter.base_url == "https://metabase.example.invalid"
    assert asyncio.run(adapter._headers()) == {"X-API-Key": "key"}
    client = Client([{"ok": True}])
    monkeypatch.setattr(module, "secure_http_client", lambda **_kwargs: client)
    assert asyncio.run(adapter._get("/api/test", {"q": "x"})) == {"ok": True}
    assert client.calls[0][1].endswith("/api/test")


def test_metabase_search_cards_dashboards_and_exports(
    monkeypatch: pytest.MonkeyPatch,
    metabase_config: SimpleNamespace,
) -> None:
    """Characterize collection filtering, reads, execution, and export validation."""
    adapter = MetabaseClient(settings)
    routes = {
        "/api/search": {
            "data": [
                {"id": 1, "collection_id": 1},
                {"id": 2, "collection": {"id": 2}},
                {"id": 3, "collection_id": 9},
            ]
        },
        "/api/card/1": {"id": 1, "collection_id": 1},
        "/api/dashboard/2": {"id": 2, "collection_id": 2},
    }

    async def get(path: str, _params=None):
        """Return route-specific metadata."""
        return routes[path]

    monkeypatch.setattr(adapter, "_get", get)
    assert asyncio.run(adapter.search("sales"))["row_count"] == 2
    assert asyncio.run(adapter.search("sales", ["card"]))["row_count"] == 2
    assert asyncio.run(adapter.get_card(1))["id"] == 1
    assert asyncio.run(adapter.get_dashboard(2))["id"] == 2

    client = Client([[{"id": 1}, {"id": 2}], [{"id": 1}]])
    monkeypatch.setattr(module, "secure_http_client", lambda **_kwargs: client)
    assert asyncio.run(adapter.run_card(1))["truncated"] is True
    exported = asyncio.run(adapter.export_card(1, "outputs/card.json", [{"id": "p"}], "json"))
    assert exported["row_count"] == 1
    with pytest.raises(ValueError, match="format"):
        asyncio.run(adapter.export_card(1, "outputs/card.xml", export_format="xml"))
    with pytest.raises(ValueError, match="end with"):
        asyncio.run(adapter.export_card(1, "outputs/card.txt", export_format="csv"))


def test_metabase_native_query(
    monkeypatch: pytest.MonkeyPatch,
    metabase_config: SimpleNamespace,
) -> None:
    """Characterize database scope and native-query result normalization."""
    adapter = MetabaseClient(settings)
    payload = {
        "data": {
            "cols": [{"name": "id"}, {"display_name": "Total"}, {}],
            "rows": [[1, 2, 3], [4, 5]],
        }
    }
    client = Client([payload, []])
    monkeypatch.setattr(module, "secure_http_client", lambda **_kwargs: client)
    result = asyncio.run(adapter.query(10, "SELECT * FROM public.orders"))
    assert result["columns"] == ["id", "Total", "column_3"]
    assert result["rows"] == [{"id": 1, "Total": 2, "column_3": 3}]
    result = asyncio.run(adapter.query(10, "SELECT * FROM public.orders"))
    assert result["columns"] == []
    with pytest.raises(ValueError, match="database is not allowed"):
        asyncio.run(adapter.query(11, "SELECT 1"))


def test_metabase_collections_and_metadata(
    monkeypatch: pytest.MonkeyPatch,
    metabase_config: SimpleNamespace,
) -> None:
    """Characterize collections, database metadata, and field-table fallback."""
    adapter = MetabaseClient(settings)
    responses = {
        "/api/collection": [
            {"id": 1, "parent_id": None},
            {"id": 2, "parent_id": 1},
            {"id": 9, "parent_id": 1},
        ],
        "/api/collection/1/items": {"data": [{"id": 1}, {"id": 2}]},
        "/api/database/10/metadata": {"tables": []},
        "/api/table/1": {"id": 1, "db_id": 10},
        "/api/field/2": {"id": 2, "table_id": 1},
        "/api/table/3": {"db_id": 10},
    }

    async def get(path: str, _params=None):
        """Return route-specific collection or metadata payloads."""
        return responses[path]

    monkeypatch.setattr(adapter, "_get", get)
    assert asyncio.run(adapter.list_collections())["row_count"] == 2
    assert asyncio.run(adapter.list_collections(1))["rows"] == [{"id": 2, "parent_id": 1}]
    assert asyncio.run(adapter.list_collection_items(1))["truncated"] is True
    assert asyncio.run(adapter.list_collection_items(1, ["card"]))["row_count"] == 2
    assert adapter._allow_collection(1) == 1
    assert adapter._allow_database(10) == 10
    assert asyncio.run(adapter.get_database_metadata(10)) == {"tables": []}
    assert asyncio.run(adapter.get_table_metadata(1))["db_id"] == 10
    assert asyncio.run(adapter.get_field_metadata(2))["table_id"] == 1

    with pytest.raises(ValueError, match="Root"):
        adapter._allow_collection(None)
    with pytest.raises(ValueError, match="not allowed"):
        asyncio.run(adapter.list_collections(9))
    with pytest.raises(ValueError, match="not allowed"):
        asyncio.run(adapter.list_collection_items(9))

    monkeypatch.setattr(adapter, "_get", _async_non_list)
    with pytest.raises(TypeError, match="unexpected"):
        asyncio.run(adapter.list_collections())


def test_metabase_metadata_failures(
    monkeypatch: pytest.MonkeyPatch,
    metabase_config: SimpleNamespace,
) -> None:
    """Characterize missing database ownership and malformed field-table responses."""
    adapter = MetabaseClient(settings)
    queue = [{"table_id": 1}, "invalid"]

    async def malformed(_path: str, _params=None):
        """Return queued malformed field metadata."""
        return queue.pop(0)

    monkeypatch.setattr(adapter, "_get", malformed)
    with pytest.raises(RuntimeError, match="unexpected"):
        asyncio.run(adapter.get_field_metadata(1))

    monkeypatch.setattr(adapter, "_get", lambda *_args: _async_value({"id": 1}))
    with pytest.raises(RuntimeError, match="does not identify"):
        asyncio.run(adapter.get_table_metadata(1))

    metabase_config.metabase_collection_ids = []
    with pytest.raises(RuntimeError, match="No Metabase collections"):
        adapter._allowed_collections()


def test_metabase_subscriptions_permissions_and_settings(
    monkeypatch: pytest.MonkeyPatch,
    metabase_config: SimpleNamespace,
) -> None:
    """Characterize subscriptions, permission filtering, and safe settings."""
    adapter = MetabaseClient(settings)
    monkeypatch.setattr(adapter, "get_dashboard", lambda *_args: _async_value({"id": 2}))
    queue = [
        [{"id": 1}, {"id": 2}],
        {"data": [{"id": 3}]},
        {
            "revision": 7,
            "groups": {
                "1": {"root": "read", "1": "read", "other": "write"},
                "2": {"other": "none"},
                "3": "invalid",
            },
        },
        [
            {"key": "site-name", "value": "BI", "is_env_setting": False},
            {"key": "site-name", "value": "hidden", "is_env_setting": True},
            {"key": "unsafe", "value": "hidden"},
        ],
        {},
    ]

    async def get(_path: str, _params=None):
        """Return ordered auxiliary endpoint payloads."""
        return queue.pop(0)

    monkeypatch.setattr(adapter, "_get", get)
    assert asyncio.run(adapter.list_dashboard_subscriptions(2))["row_count"] == 2
    assert asyncio.run(adapter.list_dashboard_subscriptions(2))["rows"] == [{"id": 3}]
    permissions = asyncio.run(adapter.get_collection_permissions(1))
    assert permissions == {"revision": 7, "groups": {"1": {"root": "read", "1": "read"}}}
    assert asyncio.run(adapter.get_safe_settings()) == {"site-name": "BI"}
    assert asyncio.run(adapter.get_safe_settings()) == {}


def test_metabase_non_mapping_permissions_failure(
    monkeypatch: pytest.MonkeyPatch,
    metabase_config: SimpleNamespace,
) -> None:
    """Characterize the current malformed permission-graph failure."""
    adapter = MetabaseClient(settings)
    monkeypatch.setattr(adapter, "_get", lambda *_args: _async_value([]))
    with pytest.raises(AttributeError):
        asyncio.run(adapter.get_collection_permissions(1))


async def _async_value(value):
    """Return a value from a minimal awaitable."""
    return value


async def _async_non_list(*_args):
    """Return a non-list collection payload."""
    return {"data": []}


def test_username_password_is_exchanged_for_memory_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exchange username and password credentials once for an in-memory session."""
    monkeypatch.setattr(
        type(settings),
        "optional_credential",
        lambda self, source, alias="default": {
            "url": "https://metabase.example.invalid",
            "username": "user@example.invalid",
            "password": "secret",
        },
    )

    class SessionResponse:
        """Provide a successful Metabase session response."""

        @staticmethod
        def raise_for_status() -> None:
            """Represent a successful response."""

        @staticmethod
        def json() -> dict:
            """Return a generated session identifier."""
            return {"id": "session-id"}

    class SessionClient:
        """Provide the Metabase session exchange."""

        async def __aenter__(self):
            """Enter the asynchronous test context."""
            return self

        async def __aexit__(self, *_args) -> None:
            """Exit the asynchronous test context."""

        async def post(self, url: str, json: dict) -> SessionResponse:
            """Validate the session request and return its response."""
            assert url == "https://metabase.example.invalid/api/session"
            assert set(json) == {"username", "password"}
            return SessionResponse()

    monkeypatch.setattr(module, "secure_http_client", lambda **_kwargs: SessionClient())
    adapter = MetabaseClient(settings)
    first = asyncio.run(adapter._headers())
    second = asyncio.run(adapter._headers())
    assert first == second == {"X-Metabase-Session": "session-id"}
