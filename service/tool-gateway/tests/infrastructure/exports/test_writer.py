"""Test bounded tabular export serialization."""

import csv
import json
from pathlib import Path

import pytest

from tool_gateway.infrastructure.configuration.settings import Settings
from tool_gateway.infrastructure.exports.paths import ExportPathResolver
from tool_gateway.infrastructure.exports.writer import TabularExporter

settings = Settings()


def configure_exporter(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, TabularExporter]:
    """Create an exporter backed by an isolated workspace."""
    monkeypatch.setattr(settings, "agent_data_dir", tmp_path)
    root = tmp_path / "assistant/workspace"
    root.mkdir(parents=True)
    return root, TabularExporter(settings, ExportPathResolver(settings))


def test_write_serializes_json_inside_structured_output_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Write JSON below outputs and reject workspace-root destinations."""
    root, exporter = configure_exporter(tmp_path, monkeypatch)
    result = exporter.write([{"value": 1}], "outputs/2026-08-16/test/result.json")
    assert result["row_count"] == 1
    assert json.loads((root / "outputs/2026-08-16/test/result.json").read_text()) == [
        {"value": 1}
    ]
    with pytest.raises(ValueError, match="outputs"):
        exporter.write([{"value": 1}], "result.json")


def test_write_serializes_csv_and_enforces_row_and_byte_limits(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Write CSV and remove outputs that exceed configured bounds."""
    root, exporter = configure_exporter(tmp_path, monkeypatch)
    monkeypatch.setattr(settings, "tool_export_max_rows", 1)
    with pytest.raises(ValueError, match="MAX_ROWS"):
        exporter.write([{"a": 1}, {"a": 2}], "outputs/result.csv")

    monkeypatch.setattr(settings, "tool_export_max_rows", 10)
    monkeypatch.setattr(settings, "tool_export_max_bytes", 1_000)
    result = exporter.write([{"b": 2, "a": 1}], "outputs/result.csv")
    with (root / "outputs/result.csv").open(encoding="utf-8-sig", newline="") as handle:
        assert list(csv.DictReader(handle)) == [{"a": "1", "b": "2"}]
    assert result["row_count"] == 1

    monkeypatch.setattr(settings, "tool_export_max_bytes", 1)
    with pytest.raises(ValueError, match="MAX_BYTES"):
        exporter.write([{"value": "long"}], "outputs/large.json")
    assert not (root / "outputs/large.json").exists()
