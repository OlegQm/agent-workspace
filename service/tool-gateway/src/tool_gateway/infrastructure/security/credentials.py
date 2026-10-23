"""Validate required integration configuration values."""


def require_config(value: str | None, name: str) -> str:
    """Return a configured value or fail closed."""
    if not value:
        raise RuntimeError(f"{name} is not configured")
    return value
