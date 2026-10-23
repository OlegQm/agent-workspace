"""Serialize bounded tabular results into workspace files."""

import csv
import json

from tool_gateway.infrastructure.configuration.settings import Settings
from tool_gateway.infrastructure.exports.paths import ExportPathResolver


class TabularExporter:
    """Serialize bounded tabular results into a role-scoped workspace."""

    def __init__(self, settings: Settings, paths: ExportPathResolver) -> None:
        """Initialize the exporter with limits and path resolution."""
        self.settings = settings
        self.paths = paths

    def write(self, rows: list[dict], destination: str, source: str = "default") -> dict:
        """Write rows as CSV or JSON after enforcing integration limits."""
        if len(rows) > self.settings.export_max_rows(source):
            raise ValueError("export exceeds TOOL_EXPORT_MAX_ROWS")
        path = self.paths.resolve(destination, {".csv", ".json"})
        if path.suffix.lower() == ".json":
            path.write_text(json.dumps(rows, ensure_ascii=False, indent=2, default=str))
        else:
            fieldnames = sorted({key for row in rows for key in row})
            with path.open("w", newline="", encoding="utf-8-sig") as handle:
                writer = csv.DictWriter(handle, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
        if path.stat().st_size > self.settings.export_max_bytes(source):
            path.unlink(missing_ok=True)
            raise ValueError("export exceeds TOOL_EXPORT_MAX_BYTES")
        return {
            "path": str(path.relative_to(self.settings.workspace)),
            "row_count": len(rows),
            "size": path.stat().st_size,
        }
