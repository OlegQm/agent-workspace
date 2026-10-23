"""Test Metabase SQL resource policy."""

import pytest

from tool_gateway.integrations.metabase.domain.policies import validate_sql_resource_scope


def test_validate_sql_resource_scope_accepts_allowlisted_patterns() -> None:
    """Accept relations matching configured wildcard patterns."""
    sql = "SELECT o.id FROM analytics_example.orders o"
    assert validate_sql_resource_scope(sql, ["analytics_example.ord*"]) == sql


def test_validate_sql_resource_scope_rejects_tables_and_columns() -> None:
    """Reject out-of-scope tables, denied columns, and unrestricted stars."""
    with pytest.raises(ValueError, match="tables are not allowed"):
        validate_sql_resource_scope(
            "SELECT id FROM analytics_example.users",
            ["analytics_example.ord*"],
        )
    with pytest.raises(ValueError, match="columns are not allowed"):
        validate_sql_resource_scope(
            "SELECT email FROM analytics_example.orders",
            ["analytics_example.ord*"],
            ["email"],
        )
    with pytest.raises(ValueError, match=r"SELECT \*"):
        validate_sql_resource_scope(
            "SELECT * FROM analytics_example.orders",
            ["analytics_example.ord*"],
            ["email"],
        )


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT account FROM analytics_example.accounts AS account",
        "SELECT row_to_json(account) FROM analytics_example.accounts AS account",
        "SELECT json_agg(account) FROM analytics_example.accounts AS account",
    ],
)
def test_validate_sql_resource_scope_rejects_whole_rows(sql: str) -> None:
    """Reject whole-row references when columns are restricted."""
    with pytest.raises(ValueError, match="Whole-row"):
        validate_sql_resource_scope(
            sql,
            ["analytics_example.accounts"],
            denied_columns=["email", "phone"],
        )


def test_validate_sql_resource_scope_handles_ctes_and_missing_scope() -> None:
    """Allow CTE aliases and reject absent or unconfigured scoped relations."""
    sql = "WITH values_cte AS (SELECT id FROM safe.contract) SELECT id FROM values_cte"
    assert validate_sql_resource_scope(sql, ["safe.contract"]) == sql
    with pytest.raises(ValueError, match="explicit schema"):
        validate_sql_resource_scope("SELECT id FROM contract", ["safe.contract"])
    with pytest.raises(ValueError, match="at least one"):
        validate_sql_resource_scope("SELECT 1", ["safe.contract"])
    with pytest.raises(RuntimeError, match="No SQL tables"):
        validate_sql_resource_scope("SELECT id FROM safe.contract", [])


def test_validate_sql_resource_scope_allows_count_star() -> None:
    """Allow COUNT star while retaining denied-column protection."""
    sql = "SELECT COUNT(*) FROM safe.contract"
    assert validate_sql_resource_scope(sql, ["safe.contract"], ["email"]) == sql
