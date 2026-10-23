"""Expose SuperFaktura use cases over an injected client."""

from typing import Any


class SuperFakturaService:
    """Delegate SuperFaktura use cases to an injected read-only client."""

    def __init__(self, client: Any) -> None:
        """Store the client dependency."""
        self.client = client

    def __getattr__(self, name: str) -> Any:
        """Expose client operations without coupling to its implementation."""
        return getattr(self.client, name)
