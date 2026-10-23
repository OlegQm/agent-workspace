"""Test Stripe client behavior without external requests."""

import asyncio
from types import SimpleNamespace

import pytest

from tool_gateway.infrastructure.configuration.settings import Settings
from tool_gateway.integrations.payments.stripe.infrastructure import client as stripe_module
from tool_gateway.integrations.payments.stripe.infrastructure.client import StripeClient

settings = Settings()


class Response:
    """Return configured Stripe JSON."""

    def __init__(self, payload: dict) -> None:
        """Store response payload."""
        self.payload = payload

    def raise_for_status(self) -> None:
        """Represent a successful response."""

    def json(self) -> dict:
        """Return response JSON."""
        return self.payload


class Client:
    """Record fake Stripe requests."""

    def __init__(self, responses: list[dict]) -> None:
        """Store ordered response payloads."""
        self.responses = responses
        self.calls: list[tuple] = []

    async def __aenter__(self):
        """Enter the fake client."""
        return self

    async def __aexit__(self, *_args) -> None:
        """Exit the fake client."""

    async def get(self, url: str, **kwargs) -> Response:
        """Record GET and return the next payload."""
        self.calls.append(("GET", url, kwargs))
        return Response(self.responses.pop(0))


@pytest.fixture
def stripe_config(monkeypatch: pytest.MonkeyPatch) -> None:
    """Configure a Stripe allowlist and fake credentials."""
    resources = SimpleNamespace(stripe_accounts=["main"])
    monkeypatch.setattr(
        Settings,
        "manifest",
        property(lambda _self: SimpleNamespace(resources=resources)),
    )
    monkeypatch.setattr(
        Settings,
        "credential",
        lambda _self, _source, _alias: {
            "restricted_key": "rk_test",
            "stripe_account": "acct_1",
        },
    )


async def _async_get(account: str, path: str, params: dict | None = None) -> dict:
    """Return arguments from a fake Stripe GET operation."""
    return {"account": account, "path": path, "params": params}


def test_operations(monkeypatch: pytest.MonkeyPatch, stripe_config: None) -> None:
    """Validate filters, IDs, request headers, and recursive redaction."""
    adapter = StripeClient(settings)
    assert adapter._redact([{"id": "pi_1", "customer": "hidden"}, 2]) == [
        {"id": "pi_1"},
        2,
    ]
    assert adapter._profile("main")["restricted_key"] == "rk_test"

    async def run() -> None:
        """Exercise asynchronous Stripe operations."""
        client = Client(
            [
                {"data": [{"id": "pi_1", "customer": "hidden"}], "secret": "hidden"},
                {"id": "ch_1", "amount": 50, "customer": "hidden"},
            ]
        )
        monkeypatch.setattr(stripe_module, "secure_http_client", lambda **_kwargs: client)
        result = await adapter.list_objects("main", "payment_intents", 1, 2, "succeeded", 500)
        assert result == {"data": [{"id": "pi_1"}]}
        assert client.calls[0][2]["headers"]["Stripe-Account"] == "acct_1"
        monkeypatch.setattr(adapter, "_get", _async_get)
        assert await adapter.list_objects("main", "refunds", limit=0) == {
            "account": "main",
            "path": "refunds",
            "params": {"limit": 1},
        }
        monkeypatch.setattr(stripe_module, "secure_http_client", lambda **_kwargs: client)
        monkeypatch.setattr(adapter, "_get", StripeClient(settings)._get)
        assert await adapter.get_object("main", "charges", "ch_1") == {
            "id": "ch_1",
            "amount": 50,
        }
        with pytest.raises(ValueError, match="object type"):
            await adapter.list_objects("main", "unknown")
        with pytest.raises(ValueError, match="status"):
            await adapter.list_objects("main", "charges", status="succeeded")
        with pytest.raises(ValueError, match="status"):
            await adapter.list_objects("main", "payment_intents", status="invalid")
        with pytest.raises(ValueError, match="object ID"):
            await adapter.get_object("main", "charges", "pi_1")

    asyncio.run(run())


def test_header_without_connected_account(
    monkeypatch: pytest.MonkeyPatch,
    stripe_config: None,
) -> None:
    """Omit the connected-account header for a direct account."""
    monkeypatch.setattr(
        Settings,
        "credential",
        lambda _self, _source, _alias: {"restricted_key": "rk_test"},
    )
    client = Client([{"id": "re_1"}])
    monkeypatch.setattr(stripe_module, "secure_http_client", lambda **_kwargs: client)
    asyncio.run(StripeClient(settings).get_object("main", "refunds", "re_1"))
    assert "Stripe-Account" not in client.calls[0][2]["headers"]


def test_redact_removes_customer_data() -> None:
    """Remove customer and billing fields recursively."""
    value = StripeClient._redact(
        {
            "id": "pi_1",
            "amount": 100,
            "customer": "cus_secret",
            "billing_details": {"email": "user@example.invalid"},
        }
    )
    assert value == {"id": "pi_1", "amount": 100}
