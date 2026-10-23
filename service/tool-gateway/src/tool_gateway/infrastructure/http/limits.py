"""Apply bounds to inline and streamed integration results."""

from pathlib import Path
from typing import Any

from tool_gateway.infrastructure.configuration.settings import Settings


class ResultLimiter:
    """Apply role-scoped limits to inline and streamed results."""

    def __init__(self, settings: Settings) -> None:
        """Initialize the limiter with result-size configuration."""
        self.settings = settings

    def limit(self, rows: list[Any]) -> dict:
        """Return a bounded inline result with total-row metadata."""
        count = len(rows)
        return {
            "rows": rows[: self.settings.tool_result_max_rows],
            "row_count": count,
            "truncated": count > self.settings.tool_result_max_rows,
        }

    @staticmethod
    async def write_stream(response: Any, path: Path, max_bytes: int) -> int:
        """Write a stream while deleting partial files that exceed the limit."""
        content_length = response.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > max_bytes:
                    raise ValueError("download exceeds TOOL_EXPORT_MAX_BYTES")
            except ValueError as exc:
                if str(exc) == "download exceeds TOOL_EXPORT_MAX_BYTES":
                    raise
                # Invalid Content-Length is ignored; the streamed limit remains authoritative.
        size = 0
        try:
            with path.open("wb") as handle:
                async for chunk in response.aiter_bytes():
                    size += len(chunk)
                    if size > max_bytes:
                        raise ValueError("download exceeds TOOL_EXPORT_MAX_BYTES")
                    handle.write(chunk)
        except Exception:
            path.unlink(missing_ok=True)
            raise
        return size
