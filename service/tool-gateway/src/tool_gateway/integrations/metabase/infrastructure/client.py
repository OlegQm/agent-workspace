"""Provide the read-only Metabase adapter."""

from collections.abc import Callable
from typing import Any, ClassVar
from urllib.parse import urlsplit

from tool_gateway.infrastructure.configuration.settings import Settings
from tool_gateway.infrastructure.exports.paths import ExportPathResolver
from tool_gateway.infrastructure.exports.writer import TabularExporter
from tool_gateway.infrastructure.http.client import secure_http_client
from tool_gateway.infrastructure.http.limits import ResultLimiter
from tool_gateway.infrastructure.security.credentials import require_config
from tool_gateway.infrastructure.security.resources import require_allowed_exact
from tool_gateway.infrastructure.security.sql import require_readonly_sql
from tool_gateway.infrastructure.security.urls import require_https_url
from tool_gateway.integrations.metabase.domain.policies import validate_sql_resource_scope


class MetabaseClient:
    """Provide read-only operations for Metabase."""

    SAFE_SETTINGS: ClassVar[set[str]] = {
        "report-timezone",
        "site-name",
        "site-url",
        "start-of-week",
        "enable-query-caching",
    }

    def __init__(
        self,
        settings: Settings,
        exporter: TabularExporter | None = None,
        limiter: ResultLimiter | None = None,
        http_client: Callable[..., Any] | None = None,
    ) -> None:
        """Initialize the client with its role-scoped configuration."""
        self.settings = settings
        self.exporter = exporter or TabularExporter(settings, ExportPathResolver(settings))
        self.limiter = limiter or ResultLimiter(settings)
        self.http_client = http_client
        profile = self.settings.optional_credential("metabase")
        configured_url = str(self.settings.metabase_url)
        configured_host = urlsplit(configured_url).hostname
        self.base_url = require_https_url(
            str(profile.get("url") or configured_url),
            allowed_hosts={configured_host} if configured_host else set(),
            label="Metabase URL",
        ).rstrip("/")
        self._session_id: str | None = None

    async def _headers(self) -> dict[str, str]:
        """Handle internal headers details."""
        profile = self.settings.optional_credential("metabase")
        key = profile.get("api_key")
        if key:
            return {"X-API-Key": str(key)}
        if not self._session_id:
            username = require_config(profile.get("username"), "Metabase username")
            password = require_config(profile.get("password"), "Metabase password")
            async with (self.http_client or secure_http_client)(timeout=30) as client:
                response = await client.post(
                    f"{self.base_url}/api/session",
                    json={"username": username, "password": password},
                )
                response.raise_for_status()
                self._session_id = require_config(response.json().get("id"), "Metabase session ID")
        return {"X-Metabase-Session": self._session_id}

    async def _get(self, path: str, params: Any = None) -> Any:
        """Return the requested data."""
        async with (self.http_client or secure_http_client)(timeout=30) as client:
            response = await client.get(
                f"{self.base_url}{path}", headers=await self._headers(), params=params
            )
            response.raise_for_status()
            return response.json()

    async def search(self, query: str, models: list[str] | None = None) -> dict:
        """Search the requested data."""
        allowed = self._allowed_collections()
        params: list[tuple[str, str]] = [("q", query)]
        for model in models or ["card", "dashboard"]:
            params.append(("models", model))
        data = await self._get("/api/search", params)
        assert isinstance(data, dict)
        rows = data.get("data", data)
        return self.limiter.limit(
            [
                row
                for row in rows
                if row.get("collection_id") in allowed
                or (row.get("collection") or {}).get("id") in allowed
            ]
        )

    async def get_card(self, card_id: int) -> dict:
        """Return card."""
        value = await self._get(f"/api/card/{card_id}")
        self._allow_collection(value.get("collection_id"))
        return value

    async def get_dashboard(self, dashboard_id: int) -> dict:
        """Return dashboard."""
        value = await self._get(f"/api/dashboard/{dashboard_id}")
        self._allow_collection(value.get("collection_id"))
        return value

    async def run_card(self, card_id: int, parameters: list[dict] | None = None) -> dict:
        """Run card."""
        await self.get_card(card_id)
        async with (self.http_client or secure_http_client)(timeout=120) as client:
            response = await client.post(
                f"{self.base_url}/api/card/{card_id}/query/json",
                headers=await self._headers(),
                json={"parameters": parameters or []},
            )
            response.raise_for_status()
            return self.limiter.limit(response.json())

    async def export_card(
        self,
        card_id: int,
        destination: str,
        parameters: list[dict] | None = None,
        export_format: str = "csv",
    ) -> dict:
        """Export card."""
        if export_format not in {"csv", "json"}:
            raise ValueError("Metabase export format must be csv or json")
        if not destination.lower().endswith(f".{export_format}"):
            raise ValueError(f"Metabase destination must end with .{export_format}")
        await self.get_card(card_id)
        async with (self.http_client or secure_http_client)(timeout=180) as client:
            response = await client.post(
                f"{self.base_url}/api/card/{card_id}/query/json",
                headers=await self._headers(),
                json={"parameters": parameters or []},
            )
            response.raise_for_status()
            return self.exporter.write(response.json(), destination, "metabase")

    async def query(self, database_id: int, sql: str) -> dict:
        """Query the requested data."""
        if database_id not in self.settings.allowed_metabase_database_ids:
            raise ValueError("Metabase database is not allowed")
        sql = require_readonly_sql(sql, "postgres")
        validate_sql_resource_scope(
            sql,
            self.settings.manifest.resources.metabase_sql_tables,
            self.settings.manifest.resources.metabase_sql_denied_columns,
        )
        payload = {
            "database": database_id,
            "type": "native",
            "native": {"query": sql, "template-tags": {}},
            "parameters": [],
        }
        async with (self.http_client or secure_http_client)(timeout=120) as client:
            response = await client.post(
                f"{self.base_url}/api/dataset",
                headers=await self._headers(),
                json=payload,
            )
            response.raise_for_status()
            value = response.json()
            data = value.get("data", {}) if isinstance(value, dict) else {}
            columns = [
                str(column.get("name") or column.get("display_name") or f"column_{index + 1}")
                for index, column in enumerate(data.get("cols", []))
            ]
            rows = [dict(zip(columns, row, strict=False)) for row in data.get("rows", [])]
            result = self.limiter.limit(rows)
            result["columns"] = columns
            return result

    async def list_collections(self, parent_id: int | None = None) -> dict:
        """List collections."""
        data = await self._get("/api/collection", {"tree": "true"})
        if not isinstance(data, list):
            raise TypeError("Metabase collection API returned an unexpected response")
        allowed = self._allowed_collections()
        rows = [row for row in data if row.get("id") in allowed]
        if parent_id is not None:
            require_allowed_exact(parent_id, list(allowed), "Metabase collection")
            rows = [row for row in rows if row.get("parent_id") == parent_id]
        return self.limiter.limit(rows)

    async def list_collection_items(
        self, collection_id: int, models: list[str] | None = None
    ) -> dict:
        """List collection items."""
        require_allowed_exact(
            collection_id,
            self.settings.manifest.resources.metabase_collection_ids,
            "Metabase collection",
        )
        params: list[tuple[str, str]] = [("models", item) for item in models or []]
        data = await self._get(f"/api/collection/{collection_id}/items", params)
        assert isinstance(data, dict)
        return self.limiter.limit(data.get("data", []))

    def _allowed_collections(self) -> set[int]:
        """Handle internal allowed collections details."""
        allowed = set(self.settings.manifest.resources.metabase_collection_ids)
        if not allowed:
            raise RuntimeError("No Metabase collections are allowlisted")
        return allowed

    def _allow_collection(self, collection_id: int | None) -> int:
        """Handle internal allow collection details."""
        if collection_id is None:
            raise ValueError("Root Metabase collection is not allowed")
        return require_allowed_exact(
            int(collection_id), list(self._allowed_collections()), "Metabase collection"
        )

    def _allow_database(self, database_id: int) -> int:
        """Handle internal allow database details."""
        return require_allowed_exact(
            database_id, self.settings.allowed_metabase_database_ids, "Metabase database"
        )

    async def get_database_metadata(self, database_id: int) -> dict:
        """Return database metadata."""
        self._allow_database(database_id)
        return await self._get(f"/api/database/{database_id}/metadata")  # type: ignore[return-value]

    async def _metadata_object(self, kind: str, object_id: int) -> dict:
        """Handle internal metadata object details."""
        value = await self._get(f"/api/{kind}/{object_id}")
        assert isinstance(value, dict)
        database_id = value.get("db_id") or value.get("database_id")
        if database_id is None and kind == "field":
            table = await self._get(f"/api/table/{value['table_id']}")
            if not isinstance(table, dict):
                raise RuntimeError("Metabase table API returned an unexpected response")
            database_id = table.get("db_id")
        if database_id is None:
            raise RuntimeError("Metabase metadata does not identify its database")
        self._allow_database(int(database_id))
        return value

    async def get_table_metadata(self, table_id: int) -> dict:
        """Return table metadata."""
        return await self._metadata_object("table", table_id)

    async def get_field_metadata(self, field_id: int) -> dict:
        """Return field metadata."""
        return await self._metadata_object("field", field_id)

    async def list_dashboard_subscriptions(self, dashboard_id: int) -> dict:
        """List dashboard subscriptions."""
        await self.get_dashboard(dashboard_id)
        data = await self._get(f"/api/pulse?dashboard_id={dashboard_id}")
        return self.limiter.limit(data if isinstance(data, list) else data.get("data", []))

    async def get_collection_permissions(self, collection_id: int) -> dict:
        """Return collection permissions."""
        require_allowed_exact(
            collection_id,
            self.settings.manifest.resources.metabase_collection_ids,
            "Metabase collection",
        )
        graph = await self._get("/api/collection/graph")
        groups = graph.get("groups", {}) if isinstance(graph, dict) else {}
        target = str(collection_id)
        filtered = {}
        for group_id, permissions in groups.items():
            if not isinstance(permissions, dict):
                continue
            values = {key: value for key, value in permissions.items() if key in {"root", target}}
            if values:
                filtered[group_id] = values
        return {"revision": graph.get("revision"), "groups": filtered}

    async def get_safe_settings(self) -> dict:
        """Return safe self.settings."""
        allowed = set(self.settings.manifest.resources.metabase_setting_keys) & self.SAFE_SETTINGS
        data = await self._get("/api/setting")
        rows = data if isinstance(data, list) else []
        return {
            row["key"]: row.get("value")
            for row in rows
            if row.get("key") in allowed and not row.get("is_env_setting")
        }
