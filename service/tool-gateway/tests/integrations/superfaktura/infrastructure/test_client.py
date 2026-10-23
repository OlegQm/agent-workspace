"""Characterize all SuperFaktura branches without external requests."""

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from tool_gateway.infrastructure.configuration.settings import Settings
from tool_gateway.integrations.superfaktura.infrastructure import client as module
from tool_gateway.integrations.superfaktura.infrastructure.client import SuperFakturaClient

settings = Settings()


class Response:
    """Provide JSON or streamed SuperFaktura response behavior."""

    def __init__(
        self,
        payload=None,
        *,
        chunks: tuple[bytes, ...] = (),
        content_type: str = "application/json",
    ) -> None:
        """Store response payload, bytes, and headers."""
        self.payload = payload
        self.chunks = chunks
        self.headers = {"content-type": content_type}

    def raise_for_status(self) -> None:
        """Represent success."""

    def json(self):
        """Return response JSON."""
        return self.payload

    async def aiter_bytes(self):
        """Yield streamed bytes."""
        for chunk in self.chunks:
            yield chunk

    async def __aenter__(self):
        """Enter the fake response stream."""
        return self

    async def __aexit__(self, *_args) -> None:
        """Exit the fake response stream."""


class Client:
    """Record fake SuperFaktura HTTP calls and streams."""

    def __init__(self, responses: list[Response]) -> None:
        """Store ordered fake responses."""
        self.responses = responses
        self.calls: list[tuple] = []

    async def __aenter__(self):
        """Enter as the fake HTTP client."""
        return self

    async def __aexit__(self, *_args) -> None:
        """Exit the fake context."""

    async def get(self, url: str, **kwargs) -> Response:
        """Record GET and return the next response."""
        self.calls.append(("GET", url, kwargs))
        return self.responses.pop(0)

    def stream(self, method: str, url: str, **kwargs):
        """Record stream and expose the next response as context."""
        self.calls.append((method, url, kwargs))
        return self.responses.pop(0)


@pytest.fixture
def superfaktura_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Configure one company and fake read credentials."""
    resources = SimpleNamespace(
        superfaktura_companies=["company"],
        superfaktura_company_labels={"company": "Company"},
        tool_export_limits={},
    )
    monkeypatch.setattr(
        Settings,
        "manifest",
        property(lambda _self: SimpleNamespace(resources=resources)),
    )
    monkeypatch.setattr(
        Settings,
        "credential",
        lambda _self, source, alias: {
            "email": f"{alias}@example.test",
            "api_key": f"{source}-key",
            "company_id": "42",
        },
    )
    monkeypatch.setattr(settings, "agent_data_dir", tmp_path)
    monkeypatch.setattr(settings, "tool_result_max_rows", 1)
    monkeypatch.setattr(Settings, "export_max_bytes", lambda _self, _source: 10_000)


def test_superfaktura_helpers_and_validation(superfaktura_config: None) -> None:
    """Characterize JSON helpers, normalization errors, profile, and list filters."""
    adapter = SuperFakturaClient(settings)
    assert adapter.list_companies() == {
        "items": [{"alias": "company", "display_name": "Company"}],
        "row_count": 1,
    }
    assert adapter._decode_json({"a": 1}) == {"a": 1}
    assert adapter._decode_json('{"a": 1}') == {"a": 1}
    assert adapter._decode_json("invalid") is None
    assert adapter._compact({"a": 1, "b": None, "c": "", "d": []}) == {"a": 1}
    with pytest.raises(TypeError, match="invoice payload"):
        adapter._invoice_record({"Invoice": []}, "company")
    with pytest.raises(TypeError, match="client payload"):
        adapter._client_record({"Client": []})
    with pytest.raises(TypeError, match="payment payload"):
        adapter._payment_record({"InvoicePayment": []})
    with pytest.raises(ValueError, match="company alias"):
        adapter._profile("default")
    with pytest.raises(ValueError, match="not allowed"):
        adapter._profile("other")
    assert adapter._profile("company")["company_id"] == "42"
    base_url, headers = adapter._connection("company")
    assert base_url == "https://moja.superfaktura.sk"
    assert "company_id=42" in headers["Authorization"]

    with pytest.raises(ValueError, match="Unsupported invoice type"):
        adapter._invoice_list_params(1, "other", None, None, None)
    assert adapter._invoice_list_params(0, "regular", None, None, None) == {
        "listinfo": 1,
        "per_page": 100,
        "page": 1,
        "type": "regular",
    }


def test_superfaktura_normalization_variants(superfaktura_config: None) -> None:
    """Characterize fallback fields and heterogeneous embedded record formats."""
    adapter = SuperFakturaClient(settings)
    invoice = adapter._invoice_record(
        {
            "invoice_no": "N",
            "variable_raw": "V",
            "home_currency": "EUR",
            "name": "unused",
        },
        "company",
    )
    assert invoice["invoice_number"] == "N"
    assert invoice["variable_symbol"] == "V"
    assert invoice["currency"] == "EUR"
    assert adapter._invoice_record({"name": "fallback"}, "company")["invoice_number"] == "fallback"

    assert adapter._invoice_items({"InvoiceItem": {"name": "A"}}) == [{"name": "A"}]
    assert adapter._invoice_items({"items": [{"description": "B", "total": 2}]}) == [
        {"name": "B", "total_without_vat": 2}
    ]
    assert adapter._invoice_items({"Invoice": {"items_data": '[{"price": 3}]'}}) == [
        {"unit_price": 3}
    ]
    assert adapter._invoice_items({"Invoice": {"items_data": '{"items":{"tax":20}}'}}) == [
        {"vat_percent": 20}
    ]
    assert adapter._invoice_items({"Invoice": {"items_data": "invalid"}}) == []
    assert adapter._invoice_items({"InvoiceItem": "invalid"}) == []
    assert adapter._invoice_items({"InvoiceItem": ["invalid"]}) == [{}]
    assert adapter._invoice_items({"InvoiceItem": [{"InvoiceItem": "invalid"}]}) == []
    assert adapter._invoice_items({}) == []

    assert adapter._invoice_client({"Client": {"id": 1}}) == {"client_id": 1}
    assert adapter._invoice_client({"Invoice": {"client_data": '[{"id":1}]'}}) is None
    assert adapter._invoice_client({"Invoice": {"client_data": "invalid"}}) is None
    assert adapter._invoice_client({"Invoice": []}) is None
    assert adapter._invoice_notes({"Invoice": []}) == {}
    payment = adapter._payment_record(
        {"paydate": "2026-01-01", "type": "card", "variable_symbol": "V"}
    )
    assert payment == {
        "date": "2026-01-01",
        "payment_type": "card",
        "variable_symbol": "V",
    }
    assert adapter._payment_record({"created": "now"}) == {"date": "now"}


def test_superfaktura_invoice_operations(
    monkeypatch: pytest.MonkeyPatch,
    superfaktura_config: None,
) -> None:
    """Characterize invoice listing, export, details, and payment aggregation."""
    adapter = SuperFakturaClient(settings)
    client = Client(
        [
            Response({"items": [{"Invoice": {"id": 1}}], "pageCount": 2}),
            Response({"items": [{"Invoice": {"id": 2}}]}),
            Response({"Invoice": {"id": 3}}),
            Response([]),
        ]
    )
    monkeypatch.setattr(module, "secure_http_client", lambda **_kwargs: client)

    async def run() -> None:
        """Exercise list and detail HTTP flows."""
        listed = await adapter.list_invoices("company", status="paid")
        assert listed == {
            "items": [{"company": "company", "company_name": "Company", "invoice_id": 1}],
            "row_count": 1,
            "page_count": 2,
        }
        exported = await adapter.list_invoices("company", destination="outputs/invoices.json")
        assert exported["row_count"] == 1 and exported["page_count"] == 1
        assert (await adapter._get_invoice_payload(3, "company"))["Invoice"]["id"] == 3
        with pytest.raises(TypeError, match="invoice response"):
            await adapter._get_invoice_payload(4, "company")

        monkeypatch.setattr(
            adapter,
            "_get_invoice_payload",
            lambda *_args: _async_value(
                {
                    "Invoice": {"id": 5, "comment": "note"},
                    "Client": {"id": 6},
                    "InvoiceItem": [{"name": "Rent"}],
                }
            ),
        )
        detailed = await adapter.get_invoice(5, "company", True, True)
        assert detailed["client"] == {"client_id": 6}
        assert detailed["notes"] == {"comment": "note"}
        basic = await adapter.get_invoice(5, "company")
        assert "client" not in basic and "notes" not in basic

        monkeypatch.setattr(
            adapter,
            "_get_invoice_payload",
            lambda *_args: _async_value(
                {
                    "payments": [{"id": 1}],
                    "payment": {"id": 2},
                    "InvoicePayment": [],
                    "invoice_payments": {"id": 3},
                }
            ),
        )
        payments = await adapter.get_invoice_payments(5, "company")
        assert payments["row_count"] == 3 and payments["truncated"] is True

    asyncio.run(run())


def test_superfaktura_client_operations(
    monkeypatch: pytest.MonkeyPatch,
    superfaktura_config: None,
) -> None:
    """Characterize client listing, contact opt-in, and malformed responses."""
    adapter = SuperFakturaClient(settings)
    client = Client(
        [
            Response({"items": [{"Client": {"id": 1, "email": "a@test"}}], "pageCount": 3}),
            Response({"Client": {"id": 2, "email": "b@test"}}),
            Response([]),
        ]
    )
    monkeypatch.setattr(module, "secure_http_client", lambda **_kwargs: client)

    async def run() -> None:
        """Exercise client HTTP flows."""
        listed = await adapter.list_clients("company", page=0, include_contact=True)
        assert listed["items"][0]["email"] == "a@test"
        assert listed["page_count"] == 3
        assert (await adapter.get_client(2, "company", True))["email"] == "b@test"
        with pytest.raises(TypeError, match="client response"):
            await adapter.get_client(3, "company")

    asyncio.run(run())


def test_superfaktura_pdf_download(
    monkeypatch: pytest.MonkeyPatch,
    superfaktura_config: None,
) -> None:
    """Characterize language/content checks and bounded PDF streaming."""
    adapter = SuperFakturaClient(settings)
    with pytest.raises(ValueError, match="language"):
        asyncio.run(adapter.download_invoice_pdf(1, "outputs/a.pdf", "xx", "company"))

    client = Client(
        [
            Response(chunks=(b"not-pdf",), content_type="text/plain"),
            Response(chunks=(b"%PDF", b"data"), content_type="application/pdf; charset=binary"),
        ]
    )
    monkeypatch.setattr(module, "secure_http_client", lambda **_kwargs: client)

    async def run() -> None:
        """Exercise rejected and successful PDF responses."""
        with pytest.raises(RuntimeError, match="did not return"):
            await adapter.download_invoice_pdf(1, "outputs/a.pdf", "eng", "company")
        result = await adapter.download_invoice_pdf(1, "outputs/a.pdf", "eng", "company")
        assert result == {"path": "outputs/a.pdf", "size": 8}
        assert (settings.workspace / result["path"]).read_bytes() == b"%PDFdata"

    asyncio.run(run())


async def _async_value(value):
    """Return a value from a minimal awaitable."""
    return value


def test_list_companies_returns_only_allowlisted_aliases(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mirror a synthetic allowlist with safe display names."""
    resources = SimpleNamespace(
        superfaktura_companies=["example-one", "example-two"],
        superfaktura_company_labels={
            "example-one": "Example Services Ltd.",
            "example-two": "Sample Trading Ltd.",
        },
    )
    manifest = SimpleNamespace(resources=resources)
    monkeypatch.setattr(Settings, "manifest", property(lambda _self: manifest))
    result = SuperFakturaClient(settings).list_companies()
    assert result["row_count"] == len(result["items"])
    assert {item["alias"] for item in result["items"]} == {
        "example-one",
        "example-two",
    }
    assert {item["display_name"] for item in result["items"]} == {
        "Example Services Ltd.",
        "Sample Trading Ltd.",
    }


def test_default_company_explains_discovery() -> None:
    """Point an invalid placeholder to company discovery."""
    with pytest.raises(ValueError, match="superfaktura_list_companies"):
        SuperFakturaClient(settings)._profile("default")


def test_invoice_normalization_omits_embedded_sensitive_data(monkeypatch: pytest.MonkeyPatch) -> None:
    """Exclude embedded client PII, credentials, and unrestricted comments."""
    resources = SimpleNamespace(
        superfaktura_companies=["example-one"],
        superfaktura_company_labels={"example-one": "Example Services Ltd."},
    )
    manifest = SimpleNamespace(resources=resources)
    monkeypatch.setattr(Settings, "manifest", property(lambda _self: manifest))
    payload = {
        "Invoice": {
            "id": "42",
            "invoice_no_formatted": "INV-EXAMPLE-42",
            "variable": "EXAMPLE-42",
            "status": "paid",
            "amount": 120.0,
            "invoice_currency": "EUR",
            "client_data": json.dumps(
                {
                    "Client": {
                        "id": "99",
                        "name": "Private Person",
                        "email": "user@example.invalid",
                        "phone": "+10000000000",
                        "address": "Private address",
                    }
                }
            ),
            "my_data": json.dumps({"Company": {"api_key": "secret-value"}}),
            "items_data": json.dumps(
                {
                    "InvoiceItem": [
                        {
                            "id": "7",
                            "name": "Example service",
                            "quantity": 1,
                            "unit_price": 100.0,
                            "tax": 20,
                        }
                    ]
                }
            ),
            "internal_comment": "Unrestricted free text",
        }
    }
    summary = SuperFakturaClient(settings)._invoice_record(payload, "example-one")
    serialized = json.dumps(summary)
    assert summary["company_name"] == "Example Services Ltd."
    assert summary["invoice_number"] == "INV-EXAMPLE-42"
    assert "Private Person" not in serialized
    assert "user@example.invalid" not in serialized
    assert "secret-value" not in serialized
    assert "Unrestricted free text" not in serialized


def test_invoice_details_require_explicit_access() -> None:
    """Keep optional client, note, and item extraction structured and bounded."""
    payload = {
        "Invoice": {
            "client_data": json.dumps(
                {
                    "Client": {
                        "id": "99",
                        "name": "Example Client",
                        "email": "user@example.invalid",
                        "address": "Private address",
                    }
                }
            ),
            "comment": "Deposit is included in the payment.",
            "items_data": json.dumps(
                {"InvoiceItem": [{"name": "Example service", "quantity": 1, "price": 50.0}]}
            ),
        }
    }
    client = SuperFakturaClient._invoice_client(payload)
    notes = SuperFakturaClient._invoice_notes(payload)
    items = SuperFakturaClient._invoice_items(payload)
    assert client == {"client_id": "99", "name": "Example Client"}
    assert "email" not in client
    assert "address" not in client
    assert notes == {"comment": "Deposit is included in the payment."}
    assert items == [{"name": "Example service", "quantity": 1, "unit_price": 50.0}]


def test_client_contact_fields_are_opt_in() -> None:
    """Exclude client contact details unless explicitly requested."""
    payload = {
        "Client": {
            "id": "99",
            "name": "Example Client",
            "email": "user@example.invalid",
            "phone": "+10000000000",
            "address": "Private address",
            "city": "Example City",
            "zip": "00000",
        }
    }
    safe = SuperFakturaClient._client_record(payload)
    detailed = SuperFakturaClient._client_record(payload, include_contact=True)
    assert "email" not in safe
    assert "phone" not in safe
    assert detailed["email"] == "user@example.invalid"
    assert detailed["postal_code"] == "00000"


def test_invoice_date_range_uses_documented_parameters() -> None:
    """Map invoice periods to SuperFaktura's from-to filter contract."""
    params = SuperFakturaClient._invoice_list_params(
        page=2,
        invoice_type="regular",
        created_from="2026-07-01",
        created_to="2026-07-31",
        status="3",
    )
    assert params == {
        "listinfo": 1,
        "per_page": 100,
        "page": 2,
        "type": "regular",
        "status": "3",
        "created": 3,
        "created_since": "2026-07-01",
        "created_to": "2026-07-31",
    }


def test_invoice_date_range_rejects_invalid_bounds() -> None:
    """Reject incomplete or reversed invoice periods."""
    with pytest.raises(ValueError, match="provided together"):
        SuperFakturaClient._invoice_list_params(1, "regular", "2026-07-01", None, None)
    with pytest.raises(ValueError, match="must not be after"):
        SuperFakturaClient._invoice_list_params(
            1,
            "regular",
            "2026-08-01",
            "2026-07-31",
            None,
        )
