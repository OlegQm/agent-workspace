"""Enforce Metabase relation and denied-column scope."""

from fnmatch import fnmatchcase

from sqlglot import exp, parse_one


def validate_sql_resource_scope(
    sql: str,
    allowed_tables: list[str],
    denied_columns: list[str] | None = None,
    dialect: str = "postgres",
) -> str:
    """Return SQL after validating relation and column scope."""
    statement = parse_one(sql, read=dialect)
    ctes = {cte.alias_or_name.lower() for cte in statement.find_all(exp.CTE)}
    relations: set[str] = set()
    for table in statement.find_all(exp.Table):
        if table.name.lower() in ctes and not table.db:
            continue
        if not table.db:
            raise ValueError("Every scoped SQL table must use an explicit schema")
        relations.add(f"{table.db}.{table.name}".lower())
    if not relations:
        raise ValueError("Query must reference at least one scoped table")
    patterns = [item.lower() for item in allowed_tables]
    if not patterns:
        raise RuntimeError("No SQL tables are allowlisted")
    outside = sorted(
        relation
        for relation in relations
        if not any(fnmatchcase(relation, pattern) for pattern in patterns)
    )
    if outside:
        raise ValueError(f"SQL tables are not allowed: {', '.join(outside)}")

    denied = {item.lower() for item in denied_columns or []}
    if denied:
        for star in statement.find_all(exp.Star):
            if not isinstance(star.parent, exp.Count):
                raise ValueError(  # noqa: TRY004 - preserve the public validation error.
                    "SELECT * is not allowed when columns are restricted"
                )
        selected = {column.name.lower() for column in statement.find_all(exp.Column)}
        blocked = sorted(selected & denied)
        if blocked:
            raise ValueError(f"SQL columns are not allowed: {', '.join(blocked)}")
        relation_names = {
            table.alias_or_name.lower()
            for table in statement.find_all(exp.Table)
            if not (table.name.lower() in ctes and not table.db)
        }
        whole_rows = sorted(selected & relation_names)
        if whole_rows:
            raise ValueError(
                "Whole-row SQL references are not allowed when columns are restricted: "
                + ", ".join(whole_rows)
            )
    return sql
