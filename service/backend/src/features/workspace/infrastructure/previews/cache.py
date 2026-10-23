"""Persist bounded document previews outside user workspaces."""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from threading import Lock

from features.workspace.infrastructure.previews.rendering import document_preview, render_pdf_page

PREVIEW_CACHE_VERSION = 1
_CACHE_LOCKS = tuple(Lock() for _ in range(64))
_PRUNE_LOCK = Lock()
_LAST_PRUNE_AT = 0.0
_PRUNE_INTERVAL_SECONDS = 300


def ensure_cache_directory(cache_dir: Path) -> None:
    """Create the private preview cache directory with restrictive permissions."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_dir.chmod(0o700)


def source_fingerprint(path: Path) -> tuple[str, int, int, int, int]:
    """Return stable file identity fields used to invalidate cached derivatives."""
    stat = path.stat()
    return (
        str(path.resolve()),
        stat.st_dev,
        stat.st_ino,
        stat.st_size,
        stat.st_mtime_ns,
    )


def cache_key(path: Path, variant: str) -> tuple[str, tuple[str, int, int, int, int]]:
    """Build an opaque cache key for one source version and preview variant."""
    fingerprint = source_fingerprint(path)
    payload = json.dumps(
        [PREVIEW_CACHE_VERSION, *fingerprint, variant],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(payload).hexdigest(), fingerprint


def cache_path(cache_dir: Path, key: str, suffix: str) -> Path:
    """Return a sharded cache path without exposing the original filename."""
    return cache_dir / key[:2] / f"{key}{suffix}"


def read_cached(path: Path, expected_prefix: bytes) -> bytes | None:
    """Read and validate a cache entry, removing incomplete artifacts."""
    try:
        content = path.read_bytes()
    except FileNotFoundError:
        return None
    if not content.startswith(expected_prefix):
        path.unlink(missing_ok=True)
        return None
    try:
        os.utime(path, None)
    except OSError:
        pass
    return content


def write_cached(path: Path, content: bytes) -> None:
    """Atomically write one private cache entry."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    descriptor, temporary_name = tempfile.mkstemp(prefix=".preview-", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.chmod(0o600)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def prune_preview_cache(cache_dir: Path, max_bytes: int, max_age_seconds: int) -> None:
    """Remove expired and least-recently-used entries until the size limit is met."""
    if not cache_dir.exists():
        return
    now = time.time()
    entries: list[tuple[Path, int, float]] = []
    total = 0
    for item in cache_dir.glob("*/*"):
        if not item.is_file():
            continue
        try:
            stat = item.stat()
        except FileNotFoundError:
            continue
        if max_age_seconds > 0 and now - stat.st_mtime > max_age_seconds:
            item.unlink(missing_ok=True)
            continue
        entries.append((item, stat.st_size, stat.st_mtime))
        total += stat.st_size
    if total <= max_bytes:
        return
    for item, size, _ in sorted(entries, key=lambda entry: entry[2]):
        item.unlink(missing_ok=True)
        total -= size
        if total <= max_bytes:
            break


def prune_preview_cache_if_due(
    cache_dir: Path,
    max_bytes: int,
    max_age_seconds: int,
) -> None:
    """Run cache maintenance at most once per interval for this backend process."""
    global _LAST_PRUNE_AT
    now = time.monotonic()
    with _PRUNE_LOCK:
        if now - _LAST_PRUNE_AT < _PRUNE_INTERVAL_SECONDS:
            return
        _LAST_PRUNE_AT = now
    prune_preview_cache(cache_dir, max_bytes, max_age_seconds)


@dataclass(frozen=True)
class PreviewCache:
    """Cache generated document previews under one bounded private directory."""

    cache_dir: Path
    max_bytes: int
    max_age_seconds: int

    def document(
        self,
        path: Path,
        sheet: str | None = None,
        compressed: bool = False,
    ) -> bytes:
        """Return a cached structured preview or generate one for this source version."""
        ensure_cache_directory(self.cache_dir)
        key, fingerprint = cache_key(path, f"document:{sheet or ''}")
        raw_target = cache_path(self.cache_dir, key, ".json")
        compressed_target = cache_path(self.cache_dir, key, ".json.gz")
        target = compressed_target if compressed else raw_target
        expected_prefix = b"\x1f\x8b" if compressed else b"{"
        lock = _CACHE_LOCKS[int(key[:2], 16) % len(_CACHE_LOCKS)]
        with lock:
            cached = read_cached(target, expected_prefix)
            if cached is not None:
                return cached
            raw_content = read_cached(raw_target, b"{")
            if raw_content is None:
                raw_content = json.dumps(
                    document_preview(path, sheet),
                    ensure_ascii=False,
                    separators=(",", ":"),
                ).encode()
                if source_fingerprint(path) == fingerprint:
                    write_cached(raw_target, raw_content)
            content = (
                gzip.compress(raw_content, compresslevel=5, mtime=0) if compressed else raw_content
            )
            if compressed and source_fingerprint(path) == fingerprint:
                write_cached(compressed_target, content)
            if source_fingerprint(path) == fingerprint:
                prune_preview_cache_if_due(
                    self.cache_dir,
                    self.max_bytes,
                    self.max_age_seconds,
                )
            return content

    def pdf_page(self, path: Path, page_number: int) -> bytes:
        """Return a cached PDF page image or render one for this source version."""
        ensure_cache_directory(self.cache_dir)
        key, fingerprint = cache_key(path, f"pdf-page:{page_number}:scale-2")
        target = cache_path(self.cache_dir, key, ".png")
        lock = _CACHE_LOCKS[int(key[:2], 16) % len(_CACHE_LOCKS)]
        with lock:
            cached = read_cached(target, b"\x89PNG\r\n\x1a\n")
            if cached is not None:
                return cached
            content = render_pdf_page(path, page_number)
            if source_fingerprint(path) == fingerprint:
                write_cached(target, content)
                prune_preview_cache_if_due(
                    self.cache_dir,
                    self.max_bytes,
                    self.max_age_seconds,
                )
            return content


def cached_document_preview(
    path: Path,
    cache_dir: Path,
    max_bytes: int,
    max_age_seconds: int,
    sheet: str | None = None,
    compressed: bool = False,
) -> bytes:
    """Return a cached structured preview through a bounded cache instance."""
    return PreviewCache(cache_dir, max_bytes, max_age_seconds).document(path, sheet, compressed)


def cached_pdf_page(
    path: Path,
    page_number: int,
    cache_dir: Path,
    max_bytes: int,
    max_age_seconds: int,
) -> bytes:
    """Return a cached PDF page through a bounded cache instance."""
    return PreviewCache(cache_dir, max_bytes, max_age_seconds).pdf_page(path, page_number)
