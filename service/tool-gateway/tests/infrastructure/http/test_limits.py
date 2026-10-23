"""Test inline and streamed result limits."""

from pathlib import Path

import pytest

from tool_gateway.infrastructure.configuration.settings import Settings
from tool_gateway.infrastructure.http.limits import ResultLimiter

settings = Settings()


class StreamResponse:
    """Provide streamed response headers and byte chunks."""

    def __init__(self, chunks: list[bytes], content_length: str | None = None) -> None:
        """Initialize response chunks and an optional Content-Length header."""
        self.chunks = chunks
        self.headers = {} if content_length is None else {"content-length": content_length}

    async def aiter_bytes(self):
        """Yield configured chunks in order."""
        for chunk in self.chunks:
            yield chunk


class FailingStreamResponse(StreamResponse):
    """Raise after yielding one chunk to exercise partial-file cleanup."""

    async def aiter_bytes(self):
        """Yield one chunk and then fail."""
        yield b"partial"
        raise OSError("stream failed")


def test_limit_returns_bounded_rows_and_total_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bound inline rows using injected settings."""
    monkeypatch.setattr(settings, "tool_result_max_rows", 1)
    limiter = ResultLimiter(settings)
    assert limiter.limit([1, 2]) == {"rows": [1], "row_count": 2, "truncated": True}
    assert limiter.limit([]) == {"rows": [], "row_count": 0, "truncated": False}


@pytest.mark.anyio
async def test_write_stream_enforces_headers_and_removes_partial_files(tmp_path: Path) -> None:
    """Enforce declared and streamed byte limits and clean failed outputs."""
    target = tmp_path / "result.bin"
    with pytest.raises(ValueError, match="TOOL_EXPORT_MAX_BYTES"):
        await ResultLimiter.write_stream(StreamResponse([], "11"), target, 10)
    assert not target.exists()

    assert await ResultLimiter.write_stream(StreamResponse([b"abc"], "invalid"), target, 10) == 3
    assert target.read_bytes() == b"abc"
    assert await ResultLimiter.write_stream(StreamResponse([b"abcd"], "4"), target, 10) == 4
    assert target.read_bytes() == b"abcd"

    with pytest.raises(ValueError, match="TOOL_EXPORT_MAX_BYTES"):
        await ResultLimiter.write_stream(StreamResponse([b"1234", b"5678"]), target, 5)
    assert not target.exists()

    with pytest.raises(OSError, match="stream failed"):
        await ResultLimiter.write_stream(FailingStreamResponse([]), target, 20)
    assert not target.exists()
