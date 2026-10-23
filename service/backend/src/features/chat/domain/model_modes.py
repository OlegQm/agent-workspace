"""Define user-facing reasoning modes independently of runtime providers."""

from enum import StrEnum


class ModelMode(StrEnum):
    """Enumerate supported ModelMode values."""

    small = "small"
    medium = "medium"
    high = "high"
