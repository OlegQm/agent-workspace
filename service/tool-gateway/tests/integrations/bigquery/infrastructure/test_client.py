"""Characterize every BigQuery adapter operation."""

from types import SimpleNamespace

import pytest
from google.cloud import bigquery as google_bigquery

from tool_gateway.infrastructure.configuration.settings import Settings
from tool_gateway.integrations.bigquery.infrastructure.client import (
    BigQueryClient as ProductionBigQueryClient,
)

settings = Settings()


class Row(dict):
    """Provide the mapping interface returned by BigQuery rows."""


class QueryResult:
    """Provide iterable BigQuery rows."""

    def __init__(self, rows: list[dict]) -> None:
        """Store rows for iteration."""
        self.rows = [Row(row) for row in rows]

    def __iter__(self):
        """Iterate over configured rows."""
        return iter(self.rows)


class QueryJob:
    """Provide dry-run metadata and regular query results."""

    def __init__(self, rows: list[dict], total_bytes_processed: int | None = 10) -> None:
        """Initialize query result data."""
        self.rows = rows
        self.total_bytes_processed = total_bytes_processed
        self.max_results: int | None = None

    def result(self, max_results: int) -> QueryResult:
        """Record the requested bound and return rows."""
        self.max_results = max_results
        return QueryResult(self.rows)


class BigQueryClient:
    """Provide all SDK calls used by the adapter."""

    def __init__(self, rows: list[dict] | None = None, total: int | None = 10) -> None:
        """Initialize fake query and metadata responses."""
        self.rows = rows or []
        self.total = total
        self.jobs: list[QueryJob] = []

    def query(self, _sql: str, job_config) -> QueryJob:
        """Return a dry or regular query job."""
        dry_run = bool(getattr(job_config, "dry_run", False))
        job = QueryJob([] if dry_run else self.rows, self.total)
        self.jobs.append(job)
        return job

    def get_dataset(self, dataset: str):
        """Return dataset metadata."""
        return SimpleNamespace(
            dataset_id=dataset.split(".")[-1],
            project=dataset.split(".")[0],
            location="EU",
            description="Dataset",
            labels={"kind": "analytics"},
            created="created",
            modified="modified",
        )

    def list_tables(self, _dataset: str):
        """Return table summaries."""
        return [SimpleNamespace(table_id="events", table_type="TABLE")]

    def get_table(self, table: str):
        """Return detailed table metadata."""
        return SimpleNamespace(
            table_id=table,
            table_type="TABLE",
            description="Events",
            labels={},
            created="created",
            modified="modified",
            num_rows=3,
            num_bytes=30,
            time_partitioning="DAY",
            range_partitioning=None,
            schema=[SimpleNamespace(to_api_repr=lambda: {"name": "id"})],
        )


@pytest.fixture
def allowed_datasets(monkeypatch: pytest.MonkeyPatch):
    """Set a deterministic dataset allowlist for one test."""
    monkeypatch.setattr(
        Settings,
        "allowed_bigquery_datasets",
        property(lambda _self: ["project.analytics"]),
    )


def test_sdk_client_and_query_validation(
    monkeypatch: pytest.MonkeyPatch,
    allowed_datasets,
) -> None:
    """Characterize SDK construction and dataset query validation."""
    sentinel = object()
    monkeypatch.setattr(google_bigquery, "Client", lambda project: (project, sentinel))
    adapter = ProductionBigQueryClient(settings)
    assert adapter._client() == (settings.google_cloud_project, sentinel)
    assert adapter._allow_dataset("project.analytics") == "project.analytics"
    with pytest.raises(ValueError, match="not allowed"):
        adapter._allow_dataset("project.private")
    assert adapter._validate("SELECT * FROM `project.analytics.events`")
    with pytest.raises(ValueError, match="allowlisted"):
        adapter._validate("SELECT 1")
    with pytest.raises(ValueError, match="allowlisted"):
        adapter._validate("SELECT * FROM `project.private.events`")

    monkeypatch.setattr(Settings, "allowed_bigquery_datasets", property(lambda _self: []))
    with pytest.raises(RuntimeError, match="No BigQuery datasets"):
        adapter._validate("SELECT * FROM `project.analytics.events`")


def test_dry_run_query_exports_and_limits(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    allowed_datasets,
) -> None:
    """Characterize dry runs, bounded inline rows, exports, and limit failures."""
    client = BigQueryClient([{"id": 1}, {"id": 2}], total=None)
    adapter = ProductionBigQueryClient(settings)
    monkeypatch.setattr(adapter, "_client", lambda: client)
    monkeypatch.setattr(settings, "agent_data_dir", tmp_path)
    monkeypatch.setattr(settings, "tool_result_max_rows", 1)
    monkeypatch.setattr(settings, "tool_export_max_rows", 2)
    monkeypatch.setattr(Settings, "export_max_rows", lambda _self, _source: 2)
    monkeypatch.setattr(settings, "bigquery_max_bytes_billed", 100)

    estimate = adapter.dry_run("SELECT * FROM `project.analytics.events`")
    assert estimate == {
        "total_bytes_processed": 0,
        "maximum_bytes_billed": 100,
        "allowed": True,
    }
    result = adapter.query("SELECT * FROM `project.analytics.events`")
    assert result == {"rows": [{"id": 1}], "row_count": 2, "truncated": True}
    exported = adapter.query(
        "SELECT * FROM `project.analytics.events`",
        "outputs/events.json",
    )
    assert exported["row_count"] == 2

    client.rows.append({"id": 3})
    with pytest.raises(ValueError, match="MAX_ROWS"):
        adapter.query(
            "SELECT * FROM `project.analytics.events`",
            "outputs/too-many.json",
        )

    client.total = 101
    with pytest.raises(ValueError, match="MAX_BYTES_BILLED"):
        adapter.query("SELECT * FROM `project.analytics.events`")


def test_bigquery_metadata_operations(
    monkeypatch: pytest.MonkeyPatch,
    allowed_datasets,
) -> None:
    """Characterize dataset, table, and partition metadata operations."""
    client = BigQueryClient([{"partition_id": "20260904"}])
    adapter = ProductionBigQueryClient(settings)
    monkeypatch.setattr(adapter, "_client", lambda: client)
    monkeypatch.setattr(adapter, "query", lambda sql: {"sql": sql})

    assert adapter.list_datasets()[0]["dataset_id"] == "analytics"
    assert adapter.get_dataset("project.analytics")["labels"] == {"kind": "analytics"}
    assert adapter.list_tables("project.analytics") == [
        {"table_id": "events", "table_type": "TABLE"}
    ]
    table = adapter.get_table("project.analytics", "events")
    assert table["num_rows"] == 3
    assert table["time_partitioning"] == "DAY"
    assert table["range_partitioning"] is None
    assert table["schema"] == [{"name": "id"}]
    partitions = adapter.list_partitions("project.analytics", "events")
    assert "INFORMATION_SCHEMA.PARTITIONS" in partitions["sql"]


@pytest.mark.parametrize("table", ["events_20250115", "_TABLE_SUFFIX"])
def test_table_name_accepts_identifiers(table: str) -> None:
    """Accept valid BigQuery table identifiers."""
    assert ProductionBigQueryClient._table_name(table) == table


@pytest.mark.parametrize("table", ["events' OR 1=1", "dataset.table", "events-*", "`events`"])
def test_table_name_rejects_sql_fragments(table: str) -> None:
    """Reject SQL fragments where a table identifier is required."""
    with pytest.raises(ValueError):
        ProductionBigQueryClient._table_name(table)
