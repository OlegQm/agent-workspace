"""Resolve safe output paths within the agent workspace."""

from pathlib import Path

from tool_gateway.infrastructure.configuration.settings import Settings


class ExportPathResolver:
    """Resolve export destinations within one role-scoped workspace."""

    def __init__(self, settings: Settings) -> None:
        """Initialize the resolver with workspace configuration."""
        self.settings = settings

    def resolve(self, destination: str, suffixes: set[str] | None = None) -> Path:
        """Return a non-symlink relative path below the workspace outputs directory."""
        if not destination or Path(destination).is_absolute():
            raise ValueError("destination must be a relative workspace path")
        if not Path(destination).parts or Path(destination).parts[0] != "outputs":
            raise ValueError("destination must be under outputs/")
        root = self.settings.workspace
        root.mkdir(parents=True, exist_ok=True)
        path = root / destination
        parent = path.parent.resolve()
        try:
            parent.relative_to(root)
        except ValueError as exc:
            raise ValueError("destination escapes workspace") from exc
        if path.is_symlink():
            raise ValueError("symlink destinations are not allowed")
        if suffixes and path.suffix.lower() not in suffixes:
            raise ValueError(f"destination must end with one of: {', '.join(sorted(suffixes))}")
        parent.mkdir(parents=True, exist_ok=True)
        return path
