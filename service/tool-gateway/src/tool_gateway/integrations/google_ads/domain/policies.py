"""Validate read-only Google Ads Query Language statements."""

import re


def require_select_gaql(query: str, allowed_resources: set[str] | None = None) -> str:
    """Return one SELECT-only GAQL statement for an allowed resource."""
    normalized = query.strip()
    if not re.match(r"^SELECT\b", normalized, re.IGNORECASE):
        raise ValueError("Only SELECT GAQL queries are allowed")
    if ";" in normalized.rstrip(";"):
        raise ValueError("Multiple GAQL statements are not allowed")
    normalized = normalized.rstrip(";")
    if allowed_resources is not None:
        match = re.search(r"\bFROM\s+([A-Za-z_][A-Za-z0-9_]*)\b", normalized, re.IGNORECASE)
        if not match or match.group(1).lower() not in allowed_resources:
            raise ValueError("Google Ads resource is not allowed")
    return normalized
