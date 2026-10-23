"""Define immutable values used by restricted-content enforcement."""

from dataclasses import dataclass


@dataclass(frozen=True)
class FileStamp:
    """Record inexpensive attributes used to detect changed workspace files."""

    size: int
    modified_ns: int


@dataclass(frozen=True)
class RestrictedSource:
    """Hold an ephemeral fingerprint of one restricted source file."""

    relative_path: str
    digest: str | None
    words: tuple[str, ...]
    shingles: frozenset[tuple[str, ...]]
    prohibited_excerpts: frozenset[tuple[str, ...]]


@dataclass(frozen=True)
class BlockedDerivative:
    """Describe a generated file removed for reproducing a restricted source."""

    relative_path: str
    reason: str
