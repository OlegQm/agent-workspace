"""Test restricted-content text normalization."""

from features.workspace.infrastructure.confidentiality.normalization import (
    fixed_windows,
    shingles,
    words,
)


def test_words_are_casefolded_and_split_on_underscores() -> None:
    """Normalize words consistently across document formats."""
    assert words("One_TWO three") == ("one", "two", "three")


def test_short_shingles_and_windows_are_empty() -> None:
    """Avoid comparisons when input is shorter than the requested window."""
    assert shingles(("short",)) == frozenset()
    assert fixed_windows(("short",), 2) == frozenset()


def test_shingles_and_windows_cover_every_contiguous_position() -> None:
    """Build deterministic contiguous windows for overlap detection."""
    value = tuple(f"word-{index}" for index in range(8))
    assert len(shingles(value)) == 2
    assert fixed_windows(value, 3) == frozenset(
        tuple(value[index : index + 3]) for index in range(6)
    )
