"""Record structured audit events for connected-source tool calls."""

import functools
import hashlib
import inspect
import json
import os
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from tool_gateway.infrastructure.configuration.settings import Settings


class AuditRecorder:
    """Record bounded metadata for integration calls."""

    def __init__(self, settings: Settings) -> None:
        """Initialize the recorder with role-scoped configuration."""
        self.settings = settings

    @staticmethod
    def metrics(value: Any) -> tuple[int | None, int | None]:
        """Extract row and byte counts from a tool result."""
        if isinstance(value, list):
            return len(value), None
        if not isinstance(value, dict):
            return None, None
        rows = value.get("row_count")
        size = value.get("size")
        return (rows if isinstance(rows, int) else None, size if isinstance(size, int) else None)

    def write(self, record: dict[str, Any]) -> None:
        """Append one structured record to the role's protected audit log."""
        directory = self.settings.audit_log_dir
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{self.settings.gateway_role}.jsonl"
        payload = (json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n").encode()
        fd = os.open(path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
        try:
            os.write(fd, payload)
        finally:
            os.close(fd)

    def audited(self, tool_name: str) -> Callable:
        """Decorate a tool call with structured success and failure auditing."""

        def decorator(func: Callable) -> Callable:
            """Wrap one synchronous or asynchronous tool callable."""
            signature = inspect.signature(func)

            async def invoke(*args: Any, **kwargs: Any) -> Any:
                """Invoke the tool and record bounded metadata."""
                started = time.monotonic()
                bound = signature.bind_partial(*args, **kwargs)
                bound.apply_defaults()
                record: dict[str, Any] = {
                    "timestamp": datetime.now(UTC).isoformat(),
                    "agent": self.settings.gateway_role,
                    "tool": tool_name,
                }
                for key in (
                    "connection",
                    "dataset",
                    "customer_id",
                    "account_id",
                    "workspace_id",
                    "company",
                    "repository",
                    "property_id",
                    "database_id",
                ):
                    if key in bound.arguments:
                        record["source_alias"] = str(bound.arguments[key])
                        break
                for key in ("sql", "gaql", "query"):
                    if key in bound.arguments:
                        record["query_hash"] = hashlib.sha256(
                            str(bound.arguments[key]).encode()
                        ).hexdigest()
                        break
                try:
                    result = func(*args, **kwargs)
                    if inspect.isawaitable(result):
                        result = await result
                    rows, size = self.metrics(result)
                    record.update(status="ok", row_count=rows, byte_count=size)
                    return result
                except Exception as exc:
                    record.update(status="error", error_type=type(exc).__name__)
                    raise
                finally:
                    record["duration_ms"] = round((time.monotonic() - started) * 1000, 2)
                    self.write(record)

            wrapped = functools.wraps(func)(invoke)
            wrapped.__signature__ = signature  # type: ignore[attr-defined]
            return wrapped

        return decorator
