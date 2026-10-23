"""Normalize document text for restricted-content comparisons."""

import re

SHINGLE_WORDS = 7
WORD_RE = re.compile(r"[^\W_]+", re.UNICODE)


def words(value: str) -> tuple[str, ...]:
    """Normalize text into case-insensitive words for overlap detection."""
    return tuple(item.casefold() for item in WORD_RE.findall(value))


def shingles(value: tuple[str, ...]) -> frozenset[tuple[str, ...]]:
    """Return fixed-width word shingles for substantial-copy detection."""
    if len(value) < SHINGLE_WORDS:
        return frozenset()
    return frozenset(
        tuple(value[index : index + SHINGLE_WORDS])
        for index in range(len(value) - SHINGLE_WORDS + 1)
    )


def fixed_windows(value: tuple[str, ...], width: int) -> frozenset[tuple[str, ...]]:
    """Return fixed-width contiguous windows used to enforce excerpt limits."""
    if len(value) < width:
        return frozenset()
    return frozenset(tuple(value[index : index + width]) for index in range(len(value) - width + 1))
