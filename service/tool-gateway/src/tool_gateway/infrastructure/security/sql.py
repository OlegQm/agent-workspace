"""Enforce shared read-only SQL syntax restrictions."""

import re

from sqlglot import exp, parse_one

MUTATING_SQL = re.compile(
    r"\b(INSERT|UPDATE|DELETE|MERGE|ALTER|DROP|TRUNCATE|CREATE|GRANT|REVOKE|CALL|COPY|EXECUTE|DO|SET)\b",
    re.IGNORECASE,
)
FORBIDDEN_EXPRESSIONS = (
    exp.Alter,
    exp.Command,
    exp.Copy,
    exp.Create,
    exp.Delete,
    exp.Drop,
    exp.Insert,
    exp.Merge,
    exp.Set,
    exp.TruncateTable,
    exp.Update,
)
FORBIDDEN_SELECT_FUNCTIONS = {
    "dblink",
    "dblink_connect",
    "dblink_connect_u",
    "dblink_disconnect",
    "lo_export",
    "lo_import",
    "nextval",
    "pg_cancel_backend",
    "pg_log_backend_memory_contexts",
    "pg_read_binary_file",
    "pg_read_file",
    "pg_reload_conf",
    "pg_rotate_logfile",
    "pg_terminate_backend",
    "set_config",
    "setval",
}


def require_readonly_sql(sql: str, dialect: str | None = None) -> str:
    """Return one parsed SELECT/WITH statement without known mutations."""
    normalized = sql.strip()
    if not normalized or not re.match(r"^(SELECT|WITH)\b", normalized, re.IGNORECASE):
        raise ValueError("Only SELECT or WITH queries are allowed")
    if MUTATING_SQL.search(normalized):
        raise ValueError("Mutating SQL is not allowed")
    without_trailing = normalized.rstrip(";").strip()
    if ";" in without_trailing:
        raise ValueError("Multiple SQL statements are not allowed")
    try:
        statement = parse_one(without_trailing, read=dialect)
    except Exception as exc:
        raise ValueError("SQL could not be parsed safely") from exc
    if statement.find(*FORBIDDEN_EXPRESSIONS):
        raise ValueError("Mutating SQL is not allowed")
    if isinstance(statement, exp.Select) and (
        statement.args.get("into") or statement.args.get("locks")
    ):
        raise ValueError("SELECT INTO and row locks are not allowed")
    for function in statement.find_all(exp.Func):
        name = (
            function.name if isinstance(function, exp.Anonymous) else function.sql_name()
        ).lower()
        if name in FORBIDDEN_SELECT_FUNCTIONS or name.startswith(("dblink_", "http_")):
            raise ValueError(f"SQL function {name} is not allowed")
    return without_trailing


def referenced_bigquery_datasets(sql: str) -> set[str]:
    """Return all explicitly referenced BigQuery datasets."""
    statement = parse_one(sql, read="bigquery")
    datasets: set[str] = set()
    for table in statement.find_all(exp.Table):
        if table.db:
            datasets.add(f"{table.catalog}.{table.db}" if table.catalog else table.db)
    return datasets
