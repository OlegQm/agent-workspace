"""Test persistent bounded document preview caching."""

import gzip
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from features.workspace.infrastructure.previews import cache as preview_cache
from features.workspace.infrastructure.previews.cache import (
    cache_key,
    cache_path,
    cached_document_preview,
    cached_pdf_page,
    ensure_cache_directory,
    prune_preview_cache,
    read_cached,
    source_fingerprint,
    write_cached,
)


def test_cache_paths_and_fingerprints_are_stable_and_opaque(tmp_path: Path) -> None:
    """Build stable opaque cache identities without exposing source names."""
    source = tmp_path / "sensitive report.xlsx"
    source.write_bytes(b"source")
    fingerprint = source_fingerprint(source)
    key, keyed_fingerprint = cache_key(source, "document:Summary")
    target = cache_path(tmp_path / "cache", key, ".json")

    assert keyed_fingerprint == fingerprint
    assert len(key) == 64
    assert target.parent.name == key[:2]
    assert source.name not in target.as_posix()


def test_structured_preview_is_cached_until_source_changes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reuse structured previews and invalidate them when the source changes."""
    source = tmp_path / "report.xlsx"
    source.write_bytes(b"first source")
    cache = tmp_path / "cache"
    calls = 0

    def fake_document_preview(path: Path, sheet: str | None = None) -> dict:
        """Return a deterministic preview while counting parser invocations."""
        nonlocal calls
        calls += 1
        return {"kind": "xlsx", "sheet": sheet, "size": path.stat().st_size}

    monkeypatch.setattr(preview_cache, "document_preview", fake_document_preview)
    first = json.loads(cached_document_preview(source, cache, 1_000_000, 3600, "Summary"))
    second = json.loads(cached_document_preview(source, cache, 1_000_000, 3600, "Summary"))
    assert first == second
    assert calls == 1

    compressed = cached_document_preview(
        source,
        cache,
        1_000_000,
        3600,
        "Summary",
        compressed=True,
    )
    assert json.loads(gzip.decompress(compressed)) == first
    assert calls == 1

    source.write_bytes(b"changed source with a different size")
    changed = json.loads(cached_document_preview(source, cache, 1_000_000, 3600, "Summary"))
    assert changed["size"] == source.stat().st_size
    assert calls == 2


def test_pdf_page_is_rendered_once_per_source_version(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cache rendered PDF pages without storing the source filename in cache paths."""
    source = tmp_path / "report.pdf"
    source.write_bytes(b"pdf source")
    cache = tmp_path / "cache"
    calls = 0

    def fake_render_pdf_page(path: Path, page_number: int) -> bytes:
        """Return a valid PNG prefix and count renderer invocations."""
        nonlocal calls
        calls += 1
        return b"\x89PNG\r\n\x1a\n" + f"{path.stat().st_size}:{page_number}".encode()

    monkeypatch.setattr(preview_cache, "render_pdf_page", fake_render_pdf_page)
    first = cached_pdf_page(source, 2, cache, 1_000_000, 3600)
    second = cached_pdf_page(source, 2, cache, 1_000_000, 3600)
    assert first == second
    assert calls == 1
    assert all(source.name not in path.name for path in cache.glob("*/*"))


def test_cache_read_write_corruption_and_pruning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Preserve atomic cache IO, corruption cleanup, expiry, and pruning throttling."""
    cache = tmp_path / "cache"
    assert read_cached(cache / "missing.json", b"{") is None
    ensure_cache_directory(cache)
    assert cache.stat().st_mode & 0o777 == 0o700
    target = cache_path(cache, "a" * 64, ".json")
    write_cached(target, b'{"ok":true}')
    assert target.stat().st_mode & 0o777 == 0o600
    assert read_cached(target, b"{") == b'{"ok":true}'
    target.write_bytes(b"broken")
    assert read_cached(target, b"{") is None

    write_cached(target, b"{}")
    with monkeypatch.context() as context:
        context.setattr(preview_cache.os, "utime", lambda *_: (_ for _ in ()).throw(OSError()))
        assert read_cached(target, b"{") == b"{}"
    prune_preview_cache(tmp_path / "absent", 1, 1)

    old = cache_path(cache, "c" * 64, ".json")
    new = cache_path(cache, "d" * 64, ".json")
    write_cached(old, b"old")
    write_cached(new, b"new")
    os.utime(old, (0, 0))
    os.utime(new, (0, 0))
    monkeypatch.setattr(preview_cache.time, "time", lambda: 1000.0)
    prune_preview_cache(cache, 0, 1)
    assert not old.exists()
    assert not new.exists()

    calls: list[tuple[Path, int, int]] = []
    monkeypatch.setattr(preview_cache, "prune_preview_cache", lambda *args: calls.append(args))
    monkeypatch.setattr(preview_cache, "_LAST_PRUNE_AT", 0.0)
    monkeypatch.setattr(preview_cache.time, "monotonic", lambda: 1_000.0)
    preview_cache.prune_preview_cache_if_due(cache, 10, 2)
    preview_cache.prune_preview_cache_if_due(cache, 10, 2)
    assert calls == [(cache, 10, 2)]


def test_cache_races_eviction_and_source_change_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Preserve pruning races, LRU eviction, and source-change no-cache behavior."""

    class VanishedEntry:
        """Represent a cache entry deleted between scan and metadata lookup."""

        def is_file(self) -> bool:
            """Report a regular file before the race occurs."""
            return True

        def stat(self):
            """Raise the filesystem race handled by cache pruning."""
            raise FileNotFoundError

    class RaceDirectory:
        """Expose one vanished entry through the path-like cache interface."""

        def exists(self) -> bool:
            """Report that the cache root exists."""
            return True

        def glob(self, _: str):
            """Return the simulated disappeared entry."""
            return [SimpleNamespace(is_file=lambda: False), VanishedEntry()]

    prune_preview_cache(RaceDirectory(), 1, 1)
    cache = tmp_path / "cache"
    ensure_cache_directory(cache)
    first = cache_path(cache, "e" * 64, ".json")
    second = cache_path(cache, "f" * 64, ".json")
    write_cached(first, b"aa")
    write_cached(second, b"bb")
    os.utime(first, (900, 900))
    os.utime(second, (901, 901))
    monkeypatch.setattr(preview_cache.time, "time", lambda: 1000.0)
    prune_preview_cache(cache, 2, 0)
    assert not first.exists()
    assert second.exists()
    prune_preview_cache(cache, 0, 0)
    assert not second.exists()

    third = cache_path(cache, "1" * 64, ".json")
    fourth = cache_path(cache, "2" * 64, ".json")
    write_cached(third, b"aa")
    write_cached(fourth, b"bb")
    prune_preview_cache(cache, -1, 0)
    assert not third.exists()
    assert not fourth.exists()

    source = tmp_path / "source.xlsx"
    source.write_bytes(b"source")
    fingerprints = iter(
        [
            ("first", 1, 1, 1, 1),
            ("second", 1, 1, 1, 2),
            ("third", 1, 1, 1, 3),
            ("fourth", 1, 1, 1, 4),
        ]
    )
    monkeypatch.setattr(preview_cache, "source_fingerprint", lambda _: next(fingerprints))
    monkeypatch.setattr(preview_cache, "document_preview", lambda *_: {"kind": "xlsx"})
    assert json.loads(cached_document_preview(source, cache, 10, 1)) == {"kind": "xlsx"}
    assert list(cache.glob("*/*.json")) == []

    image_fingerprints = iter(
        [
            ("image-first", 1, 1, 1, 1),
            ("image-second", 1, 1, 1, 2),
        ]
    )
    monkeypatch.setattr(preview_cache, "source_fingerprint", lambda _: next(image_fingerprints))
    monkeypatch.setattr(preview_cache, "render_pdf_page", lambda *_: b"\x89PNG\r\n\x1a\nimage")
    assert cached_pdf_page(source, 1, cache, 10, 1).endswith(b"image")
    assert list(cache.glob("*/*.png")) == []
