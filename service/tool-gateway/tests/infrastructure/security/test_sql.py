"""Test shared read-only SQL validation."""

from types import SimpleNamespace

import pytest

from tool_gateway.infrastructure.security import sql as security
from tool_gateway.infrastructure.security.sql import (
    referenced_bigquery_datasets,
    require_readonly_sql,
)


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM customers",
        "WITH removed AS (DELETE FROM customers RETURNING *) SELECT * FROM removed",
        "SELECT 1; DROP TABLE customers",
        "CREATE TABLE copied AS SELECT 1",
    ],
)
def test_require_readonly_sql_rejects_mutations(sql: str) -> None:
    """Reject direct, nested, and multi-statement mutations."""
    with pytest.raises(ValueError):
        require_readonly_sql(sql, "postgres")


def test_require_readonly_sql_accepts_cte() -> None:
    """Accept a read-only common table expression."""
    sql = "WITH totals AS (SELECT 1 AS value) SELECT value FROM totals"
    assert require_readonly_sql(sql, "postgres") == sql


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT pg_read_file('/etc/passwd')",
        "SELECT set_config('x', 'y', false)",
        "SELECT * FROM safe.contract FOR UPDATE",
        "SELECT 1 INTO temporary result",
        "SELECT * FROM safe.contract FOR SHARE",
        "SELECT dblink_exec('connection', 'query')",
        "SELECT pg_read_binary_file('/tmp/value')",
    ],
)
def test_require_readonly_sql_rejects_select_side_effects(sql: str) -> None:
    """Reject read-like syntax that can mutate state or access server files."""
    with pytest.raises(ValueError):
        require_readonly_sql(sql, "postgres")


@pytest.mark.parametrize("sql", ["", "VALUES (1)", "SELECT 1; SELECT 2", "SELECT ("])
def test_require_readonly_sql_rejects_invalid_statements(sql: str) -> None:
    """Reject empty, unsupported, multiple, and unparsable statements."""
    with pytest.raises(ValueError):
        require_readonly_sql(sql, "postgres")


def test_ast_guard_is_independent_of_keyword_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reject parsed mutations even when the keyword pre-check is bypassed."""
    monkeypatch.setattr(security, "MUTATING_SQL", SimpleNamespace(search=lambda _value: None))
    with pytest.raises(ValueError, match="Mutating SQL"):
        require_readonly_sql(
            "WITH removed AS (DELETE FROM safe.contract RETURNING id) SELECT id FROM removed",
            "postgres",
        )
    assert require_readonly_sql("SELECT COUNT(*) FROM safe.contract", "postgres") == (
        "SELECT COUNT(*) FROM safe.contract"
    )


def test_referenced_bigquery_datasets_collects_only_qualified_relations() -> None:
    """Collect every qualified dataset and ignore unqualified tables."""
    sql = "SELECT * FROM `prod.ga4.events` JOIN `prod.ads.campaigns` USING (campaign_id)"
    assert referenced_bigquery_datasets(sql) == {"prod.ga4", "prod.ads"}
    assert referenced_bigquery_datasets(
        "SELECT * FROM local JOIN `project.analytics.events` USING (id)"
    ) == {"project.analytics"}
