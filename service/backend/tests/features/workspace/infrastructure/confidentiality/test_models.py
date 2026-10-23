"""Test immutable restricted-content values."""

from features.workspace.infrastructure.confidentiality.models import (
    BlockedDerivative,
    FileStamp,
    RestrictedSource,
)


def test_confidentiality_values_preserve_fingerprint_data() -> None:
    """Keep snapshot, source, and blocked-derivative data explicit and immutable."""
    stamp = FileStamp(size=1, modified_ns=2)
    source = RestrictedSource(
        relative_path="private.txt",
        digest="digest",
        words=("private",),
        shingles=frozenset(),
        prohibited_excerpts=frozenset(),
    )
    blocked = BlockedDerivative(relative_path="copy.txt", reason="exact restricted copy")

    assert stamp == FileStamp(size=1, modified_ns=2)
    assert source.relative_path == "private.txt"
    assert blocked.reason == "exact restricted copy"
