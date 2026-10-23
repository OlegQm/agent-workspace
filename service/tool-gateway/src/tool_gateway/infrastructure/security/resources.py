"""Validate role-scoped integration resource identifiers."""


def require_allowed(value: str, allowed: list[str], label: str) -> str:
    """Return a normalized identifier when it is allowlisted."""
    normalized = value.replace("-", "").removeprefix("act_")
    normalized_allowed = {item.replace("-", "").removeprefix("act_") for item in allowed}
    if normalized not in normalized_allowed:
        raise ValueError(f"{label} is not allowed for this agent")
    return normalized


def require_allowed_exact[AllowedValue: (str, int)](
    value: AllowedValue,
    allowed: list[AllowedValue],
    label: str,
) -> AllowedValue:
    """Return a value only when its exact representation is allowlisted."""
    if value not in allowed:
        raise ValueError(f"{label} is not allowed for this agent")
    return value
