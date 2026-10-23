"""Characterize structured Tool Gateway auditing."""

import asyncio
import json
from pathlib import Path

import pytest

from tool_gateway.infrastructure.configuration.settings import Settings
from tool_gateway.infrastructure.observability import audit

settings = Settings()


def test_audit_metrics_and_secure_writer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Characterize metric extraction and append-only JSONL output."""
    recorder = audit.AuditRecorder(settings)
    assert recorder.metrics([1, 2]) == (2, None)
    assert recorder.metrics("value") == (None, None)
    assert recorder.metrics({"row_count": 3, "size": 4}) == (3, 4)
    assert recorder.metrics({"row_count": "3", "size": "4"}) == (None, None)

    monkeypatch.setattr(settings, "audit_log_dir", tmp_path)
    monkeypatch.setattr(settings, "gateway_role", "assistant")
    recorder.write({"event": "first"})
    recorder.write({"event": "second"})
    lines = (tmp_path / "assistant.jsonl").read_text().splitlines()
    assert [json.loads(line)["event"] for line in lines] == ["first", "second"]
    assert (tmp_path / "assistant.jsonl").stat().st_mode & 0o777 == 0o600


def test_audited_sync_call_records_source_query_and_result(monkeypatch: pytest.MonkeyPatch) -> None:
    """Record normalized metadata for a successful synchronous tool call."""
    records: list[dict] = []
    monkeypatch.setattr(settings, "gateway_role", "assistant")
    recorder = audit.AuditRecorder(settings)
    monkeypatch.setattr(recorder, "write", lambda record: records.append(record.copy()))

    @recorder.audited("query")
    def query(database_id: int, sql: str, optional: str = "default") -> dict:
        """Return a characterized result."""
        assert optional == "default"
        return {"row_count": 2, "size": 10}

    assert asyncio.run(query(7, "SELECT 1")) == {"row_count": 2, "size": 10}
    assert query.__name__ == "query"
    assert records[0]["agent"] == "assistant"
    assert records[0]["tool"] == "query"
    assert records[0]["source_alias"] == "7"
    assert len(records[0]["query_hash"]) == 64
    assert records[0]["status"] == "ok"
    assert records[0]["row_count"] == 2
    assert records[0]["byte_count"] == 10
    assert records[0]["duration_ms"] >= 0


def test_audited_async_and_error_calls_are_recorded(monkeypatch: pytest.MonkeyPatch) -> None:
    """Record awaitable results and exception types without swallowing errors."""
    records: list[dict] = []
    recorder = audit.AuditRecorder(settings)
    monkeypatch.setattr(recorder, "write", lambda record: records.append(record.copy()))

    @recorder.audited("async-list")
    async def async_list(repository: str) -> list[int]:
        """Return an awaitable list."""
        await asyncio.sleep(0)
        return [1, 2]

    @recorder.audited("failure")
    def failure() -> None:
        """Raise a characterized failure."""
        raise LookupError("failed")

    assert asyncio.run(async_list("backend")) == [1, 2]
    with pytest.raises(LookupError, match="failed"):
        asyncio.run(failure())
    assert records[0]["source_alias"] == "backend"
    assert records[0]["row_count"] == 2
    assert records[1]["status"] == "error"
    assert records[1]["error_type"] == "LookupError"
