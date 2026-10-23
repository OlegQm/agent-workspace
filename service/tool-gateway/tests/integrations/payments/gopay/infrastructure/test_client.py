"""Test GoPay client behavior without external requests."""

import asyncio
from types import SimpleNamespace

import pytest

from tool_gateway.infrastructure.configuration.settings import Settings
from tool_gateway.integrations.payments.gopay.infrastructure import client as gopay_module
from tool_gateway.integrations.payments.gopay.infrastructure.client import GoPayClient

settings = Settings()


class Response:
    """Return configured GoPay JSON."""

    def __init__(self, payload: dict) -> None:
        """Store response payload."""
        self.payload = payload

    def raise_for_status(self) -> None:
        """Represent a successful response."""

    def json(self) -> dict:
        """Return response JSON."""
        return self.payload


class Client:
    """Record fake GoPay requests."""

    def __init__(self, responses: list[dict]) -> None:
        """Store ordered response payloads."""
        self.responses = responses

    async def __aenter__(self):
        """Enter the fake client."""
        return self

    async def __aexit__(self, *_args) -> None:
        """Exit the fake client."""

    async def post(self, _url: str, **_kwargs) -> Response:
        """Return the next POST response."""
        return Response(self.responses.pop(0))

    async def get(self, _url: str, **_kwargs) -> Response:
        """Return the next GET response."""
        return Response(self.responses.pop(0))


@pytest.fixture
def gopay_config(monkeypatch: pytest.MonkeyPatch) -> None:
    """Configure a GoPay allowlist and fake credentials."""
    resources = SimpleNamespace(gopay_accounts=["main"])
    monkeypatch.setattr(
        Settings,
        "manifest",
        property(lambda _self: SimpleNamespace(resources=resources)),
    )
    monkeypatch.setattr(
        Settings,
        "credential",
        lambda _self, _source, _alias: {"client_id": "id", "client_secret": "secret"},
    )


def test_operations(monkeypatch: pytest.MonkeyPatch, gopay_config: None) -> None:
    """Validate profiles, token exchange, fetch, batch limits, and redaction."""
    adapter = GoPayClient(settings)
    assert adapter._redact({"id": 1, "email": "secret"}) == {"id": 1}
    assert adapter._profile("main")["client_id"] == "id"
    with pytest.raises(ValueError, match="not allowed"):
        adapter._profile("other")

    async def run() -> None:
        """Exercise asynchronous GoPay operations."""
        client = Client(
            [
                {"access_token": "token"},
                {"id": 1, "state": "PAID", "payer": "hidden"},
                {"access_token": "batch-token"},
                {"id": 2, "amount": 10, "payer": "hidden"},
                {"id": 3, "amount": 20},
            ]
        )
        monkeypatch.setattr(gopay_module, "secure_http_client", lambda **_kwargs: client)
        assert await adapter.get_payment("main", "1") == {"id": 1, "state": "PAID"}
        batch = await adapter.get_payments("main", ["2", "3"])
        assert batch["row_count"] == 2
        with pytest.raises(ValueError, match="numeric"):
            await adapter.get_payment("main", "x")
        for identifiers in ([], [str(index) for index in range(101)]):
            with pytest.raises(ValueError, match="between 1 and 100"):
                await adapter.get_payments("main", identifiers)
        with pytest.raises(ValueError, match="Every"):
            await adapter.get_payments("main", ["x"])

    asyncio.run(run())
