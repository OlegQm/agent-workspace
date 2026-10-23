"""Provide assertions shared by integration application-service tests."""

from types import SimpleNamespace
from typing import Any


def assert_service_delegates(service_type: type[Any]) -> None:
    """Verify that an application service exposes its injected client operations."""
    operation = object()
    client = SimpleNamespace(operation=operation)
    assert service_type(client).operation is operation
