"""Provide the read-only BigQuery adapter."""

import re

from tool_gateway.infrastructure.configuration.settings import Settings
from tool_gateway.infrastructure.exports.paths import ExportPathResolver
from tool_gateway.infrastructure.exports.writer import TabularExporter
from tool_gateway.infrastructure.http.limits import ResultLimiter
from tool_gateway.infrastructure.security.resources import require_allowed_exact
from tool_gateway.infrastructure.security.sql import (
    referenced_bigquery_datasets,
    require_readonly_sql,
)


class BigQueryClient:
    """Provide read-only operations for BigQuery."""

    def __init__(
        self,
        settings: Settings,
        exporter: TabularExporter | None = None,
        limiter: ResultLimiter | None = None,
    ) -> None:
        """Initialize the client with its role-scoped configuration."""
        self.settings = settings
        self.exporter = exporter or TabularExporter(settings, ExportPathResolver(settings))
        self.limiter = limiter or ResultLimiter(settings)

    @staticmethod
    def _table_name(table: str) -> str:
        """Handle internal table name details."""
        if not re.fullmatch(r"[A-Za-z0-9_]+", table):
            raise ValueError("BigQuery table name contains unsupported characters")
        return table

    def _client(self):
        """Handle internal client details."""
        from google.cloud import bigquery

        return bigquery.Client(project=self.settings.google_cloud_project)

    def _allow_dataset(self, dataset: str) -> str:
        """Handle internal allow dataset details."""
        return require_allowed_exact(
            dataset, self.settings.allowed_bigquery_datasets, "BigQuery dataset"
        )

    def _validate(self, sql: str) -> str:
        """Validate the requested data."""
        sql = require_readonly_sql(sql, "bigquery")
        allowed = {item.lower().strip("`") for item in self.settings.allowed_bigquery_datasets}
        if not allowed:
            raise RuntimeError("No BigQuery datasets are allowlisted")
        referenced = referenced_bigquery_datasets(sql)
        if not referenced or any(item.lower().strip("`") not in allowed for item in referenced):
            raise ValueError("Every referenced BigQuery dataset must be allowlisted")
        return sql

    def dry_run(self, sql: str) -> dict:
        """Handle dry run."""
        from google.cloud import bigquery

        sql = self._validate(sql)
        job = self._client().query(
            sql, job_config=bigquery.QueryJobConfig(dry_run=True, use_query_cache=False)
        )
        total = job.total_bytes_processed or 0
        return {
            "total_bytes_processed": total,
            "maximum_bytes_billed": self.settings.bigquery_max_bytes_billed,
            "allowed": total <= self.settings.bigquery_max_bytes_billed,
        }

    def query(self, sql: str, destination: str | None = None) -> dict:
        """Query the requested data."""
        from google.cloud import bigquery

        sql = self._validate(sql)
        estimate = self.dry_run(sql)
        if not estimate["allowed"]:
            raise ValueError("Query exceeds BIGQUERY_MAX_BYTES_BILLED")
        config = bigquery.QueryJobConfig(
            maximum_bytes_billed=self.settings.bigquery_max_bytes_billed, use_legacy_sql=False
        )
        row_limit = (
            self.settings.export_max_rows("bigquery")
            if destination
            else self.settings.tool_result_max_rows
        )
        result = self._client().query(sql, job_config=config).result(max_results=row_limit + 1)
        rows = [dict(row.items()) for row in result]
        if destination and len(rows) > row_limit:
            raise ValueError("BigQuery export exceeds TOOL_EXPORT_MAX_ROWS")
        return (
            self.exporter.write(rows, destination, "bigquery")
            if destination
            else self.limiter.limit(rows)
        )

    def list_datasets(self) -> list[dict]:
        """List datasets."""
        client = self._client()
        result = []
        for dataset in self.settings.allowed_bigquery_datasets:
            item = client.get_dataset(dataset)
            result.append(
                {
                    "dataset_id": item.dataset_id,
                    "project": item.project,
                    "location": item.location,
                    "description": item.description,
                }
            )
        return result

    def get_dataset(self, dataset: str) -> dict:
        """Return dataset."""
        item = self._client().get_dataset(self._allow_dataset(dataset))
        return {
            "dataset_id": item.dataset_id,
            "project": item.project,
            "location": item.location,
            "description": item.description,
            "labels": item.labels,
            "created": item.created,
            "modified": item.modified,
        }

    def list_tables(self, dataset: str) -> list[dict]:
        """List tables."""
        return [
            {"table_id": table.table_id, "table_type": table.table_type}
            for table in self._client().list_tables(self._allow_dataset(dataset))
        ]

    def get_table(self, dataset: str, table: str) -> dict:
        """Return table."""
        dataset = self._allow_dataset(dataset)
        table = self._table_name(table)
        item = self._client().get_table(f"{dataset}.{table}")
        return {
            "table_id": item.table_id,
            "table_type": item.table_type,
            "description": item.description,
            "labels": item.labels,
            "created": item.created,
            "modified": item.modified,
            "num_rows": item.num_rows,
            "num_bytes": item.num_bytes,
            "time_partitioning": str(item.time_partitioning) if item.time_partitioning else None,
            "range_partitioning": str(item.range_partitioning) if item.range_partitioning else None,
            "schema": [field.to_api_repr() for field in item.schema],
        }

    def list_partitions(self, dataset: str, table: str) -> dict:
        """List partitions."""
        dataset = self._allow_dataset(dataset)
        table = self._table_name(table)
        sql = (
            "SELECT partition_id, total_rows, total_logical_bytes, last_modified_time "
            f"FROM `{dataset}.INFORMATION_SCHEMA.PARTITIONS` "
            f"WHERE table_name = '{table}' ORDER BY partition_id"
        )
        return self.query(sql)
