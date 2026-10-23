"""Provide the read-only SuperFaktura adapter."""

import json
from collections.abc import Callable
from datetime import date
from typing import Any, ClassVar

from tool_gateway.infrastructure.configuration.settings import Settings
from tool_gateway.infrastructure.exports.paths import ExportPathResolver
from tool_gateway.infrastructure.exports.writer import TabularExporter
from tool_gateway.infrastructure.http.client import secure_http_client
from tool_gateway.infrastructure.http.limits import ResultLimiter
from tool_gateway.infrastructure.security.credentials import require_config
from tool_gateway.infrastructure.security.resources import require_allowed_exact
from tool_gateway.infrastructure.security.urls import require_https_url


class SuperFakturaClient:
    """Provide read-only operations for SuperFaktura."""

    def __init__(
        self,
        settings: Settings,
        paths: ExportPathResolver | None = None,
        exporter: TabularExporter | None = None,
        limiter: ResultLimiter | None = None,
        http_client: Callable[..., Any] | None = None,
    ) -> None:
        """Initialize the client with its role-scoped configuration."""
        self.settings = settings
        self.paths = paths or ExportPathResolver(settings)
        self.exporter = exporter or TabularExporter(settings, self.paths)
        self.limiter = limiter or ResultLimiter(settings)
        self.http_client = http_client

    ALLOWED_LANGUAGES: ClassVar[set[str]] = {
        "cze",
        "deu",
        "eng",
        "hrv",
        "hun",
        "ita",
        "nld",
        "pol",
        "rom",
        "rus",
        "slo",
        "slv",
        "spa",
        "ukr",
    }

    def list_companies(self) -> dict:
        """List allowlisted aliases with safe names used for company selection."""
        aliases = self.settings.manifest.resources.superfaktura_companies
        labels = self.settings.manifest.resources.superfaktura_company_labels
        return {
            "items": [
                {"alias": alias, "display_name": labels.get(alias, "Unknown configured company")}
                for alias in aliases
            ],
            "row_count": len(aliases),
        }

    @staticmethod
    def _decode_json(value: Any) -> Any:
        """Decode a JSON snapshot while preserving already structured values."""
        if not isinstance(value, str):
            return value
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _compact(values: dict[str, Any]) -> dict[str, Any]:
        """Remove absent fields from a normalized API record."""
        return {key: value for key, value in values.items() if value not in (None, "", [])}

    def _invoice_record(self, payload: dict[str, Any], alias: str) -> dict[str, Any]:
        """Normalize an invoice without returning embedded client or company snapshots."""
        invoice = payload.get("Invoice", payload)
        if not isinstance(invoice, dict):
            raise TypeError("SuperFaktura invoice payload must be a mapping")
        return self._compact(
            {
                "company": alias,
                "company_name": self.settings.manifest.resources.superfaktura_company_labels.get(
                    alias, "Unknown configured company"
                ),
                "invoice_id": invoice.get("id"),
                "invoice_number": (
                    invoice.get("invoice_no_formatted")
                    or invoice.get("invoice_no")
                    or invoice.get("name")
                ),
                "type": invoice.get("type"),
                "parent_invoice_id": invoice.get("parent_id"),
                "proforma_id": invoice.get("proforma_id"),
                "variable_symbol": invoice.get("variable") or invoice.get("variable_raw"),
                "order_number": invoice.get("order_no"),
                "created_at": invoice.get("created"),
                "accounting_date": invoice.get("accounting_date"),
                "tax_date": invoice.get("taxdate"),
                "delivery_date": invoice.get("delivery"),
                "due_date": invoice.get("due"),
                "payment_date": invoice.get("paydate"),
                "status": invoice.get("status"),
                "paid": invoice.get("paid"),
                "payment_type": invoice.get("payment_type"),
                "currency": invoice.get("invoice_currency") or invoice.get("home_currency"),
                "amount": invoice.get("amount"),
                "vat": invoice.get("vat"),
                "total_amount": invoice.get("total_amount"),
                "amount_paid": invoice.get("amount_paid"),
                "item_count": invoice.get("items_count"),
            }
        )

    @classmethod
    def _invoice_items(cls, payload: dict[str, Any]) -> list[dict[str, Any]]:
        """Normalize invoice lines and omit unrestricted snapshots and metadata."""
        invoice = payload.get("Invoice", payload)
        candidates: Any = payload.get("InvoiceItem") or payload.get("items")
        if not candidates and isinstance(invoice, dict):
            decoded = cls._decode_json(invoice.get("items_data"))
            if isinstance(decoded, dict):
                candidates = decoded.get("InvoiceItem") or decoded.get("items")
            elif isinstance(decoded, list):
                candidates = decoded
        if not candidates:
            return []
        if isinstance(candidates, dict):
            candidates = [candidates]
        if not isinstance(candidates, list):
            return []

        rows = []
        for candidate in candidates:
            item = candidate.get("InvoiceItem", candidate) if isinstance(candidate, dict) else {}
            if not isinstance(item, dict):
                continue
            rows.append(
                cls._compact(
                    {
                        "item_id": item.get("id"),
                        "name": item.get("name") or item.get("description"),
                        "quantity": item.get("quantity"),
                        "unit": item.get("unit"),
                        "unit_price": item.get("unit_price") or item.get("price"),
                        "discount_percent": item.get("discount"),
                        "vat_percent": item.get("tax") or item.get("vat"),
                        "total_without_vat": item.get("total_without_vat") or item.get("total"),
                        "vat_amount": item.get("vat_amount"),
                        "total_with_vat": item.get("total_with_vat"),
                    }
                )
            )
        return rows

    @classmethod
    def _client_record(
        cls, payload: dict[str, Any], include_contact: bool = False
    ) -> dict[str, Any]:
        """Normalize a client and omit contact and address fields unless explicitly requested."""
        client = payload.get("Client", payload)
        if not isinstance(client, dict):
            raise TypeError("SuperFaktura client payload must be a mapping")
        result = {
            "client_id": client.get("id"),
            "name": client.get("name"),
            "company_id": client.get("ico"),
            "tax_id": client.get("dic"),
            "vat_id": client.get("ic_dph"),
            "country": client.get("country"),
            "country_id": client.get("country_id"),
        }
        if include_contact:
            result.update(
                {
                    "email": client.get("email"),
                    "phone": client.get("phone"),
                    "address": client.get("address"),
                    "city": client.get("city"),
                    "postal_code": client.get("zip"),
                }
            )
        return cls._compact(result)

    @classmethod
    def _invoice_client(cls, payload: dict[str, Any]) -> dict[str, Any] | None:
        """Read the client identity from a detailed invoice response."""
        client = payload.get("Client")
        if not client:
            invoice = payload.get("Invoice", payload)
            if isinstance(invoice, dict):
                decoded = cls._decode_json(invoice.get("client_data"))
                if isinstance(decoded, dict):
                    client = decoded.get("Client", decoded)
        if not isinstance(client, dict):
            return None
        return cls._client_record(client)

    @classmethod
    def _invoice_notes(cls, payload: dict[str, Any]) -> dict[str, Any]:
        """Return free-text invoice notes only after an explicit request."""
        invoice = payload.get("Invoice", payload)
        if not isinstance(invoice, dict):
            return {}
        return cls._compact(
            {
                "comment": invoice.get("comment"),
                "header_comment": invoice.get("header_comment"),
                "internal_comment": invoice.get("internal_comment"),
            }
        )

    @classmethod
    def _payment_record(cls, payload: dict[str, Any]) -> dict[str, Any]:
        """Normalize embedded payment information without payer contact data."""
        payment = payload.get("InvoicePayment", payload)
        if not isinstance(payment, dict):
            raise TypeError("SuperFaktura payment payload must be a mapping")
        return cls._compact(
            {
                "payment_id": payment.get("id"),
                "invoice_id": payment.get("invoice_id"),
                "date": payment.get("date") or payment.get("paydate") or payment.get("created"),
                "amount": payment.get("amount"),
                "currency": payment.get("currency"),
                "payment_type": payment.get("payment_type") or payment.get("type"),
                "status": payment.get("status"),
                "variable_symbol": payment.get("variable") or payment.get("variable_symbol"),
            }
        )

    def _profile(self, alias: str) -> dict:
        """Return credentials for an explicitly selected allowlisted company."""
        if alias == "default":
            raise ValueError(
                "SuperFaktura company alias is required; "
                "call superfaktura_list_companies and use one of its aliases"
            )
        require_allowed_exact(
            alias, self.settings.manifest.resources.superfaktura_companies, "SuperFaktura company"
        )
        return self.settings.credential("superfaktura", alias)

    def _connection(self, alias: str) -> tuple[str, dict[str, str]]:
        """Handle internal connection details."""
        profile = self._profile(alias)
        url = profile.get("api_url") or self.settings.superfaktura_api_url
        email = require_config(profile.get("email"), f"SuperFaktura {alias} email")
        key = require_config(profile.get("api_key"), f"SuperFaktura {alias} API key")
        company = require_config(profile.get("company_id"), f"SuperFaktura {alias} company ID")
        base_url = require_https_url(
            str(url),
            allowed_hosts={"moja.superfaktura.sk"},
            label="SuperFaktura API URL",
        ).rstrip("/")
        return base_url, {
            "Authorization": f"SFAPI email={email}&apikey={key}&company_id={company}&module=API"
        }

    @staticmethod
    def _invoice_list_params(
        page: int,
        invoice_type: str,
        created_from: str | None,
        created_to: str | None,
        status: str | None,
    ) -> dict[str, Any]:
        """Build documented SuperFaktura invoice filters with a bounded issue-date range."""
        if invoice_type not in {"regular", "proforma", "cancel"}:
            raise ValueError("Unsupported invoice type")
        if bool(created_from) != bool(created_to):
            raise ValueError("created_from and created_to must be provided together")
        if created_from and created_to:
            start = date.fromisoformat(created_from)
            end = date.fromisoformat(created_to)
            if start > end:
                raise ValueError("created_from must not be after created_to")

        params: dict[str, Any] = {
            "listinfo": 1,
            "per_page": 100,
            "page": max(page, 1),
            "type": invoice_type,
            "status": status,
        }
        if created_from and created_to:
            params.update(
                {
                    "created": 3,
                    "created_since": created_from,
                    "created_to": created_to,
                }
            )
        return {key: value for key, value in params.items() if value is not None}

    async def list_invoices(
        self,
        company: str = "default",
        page: int = 1,
        invoice_type: str = "regular",
        created_from: str | None = None,
        created_to: str | None = None,
        status: str | None = None,
        destination: str | None = None,
    ) -> dict:
        """List normalized invoices within an optional inclusive issue-date range."""
        base_url, headers = self._connection(company)
        params = self._invoice_list_params(page, invoice_type, created_from, created_to, status)
        async with (self.http_client or secure_http_client)(
            timeout=30,
            follow_redirects=True,
            allowed_redirect_hosts={"moja.superfaktura.sk"},
        ) as client:
            response = await client.get(
                f"{base_url}/invoices/index.json",
                headers=headers,
                params=params,
            )
            response.raise_for_status()
            data = response.json()
            rows = [self._invoice_record(item, company) for item in data.get("items", [])]
            if destination:
                result = self.exporter.write(rows, destination, "superfaktura")
                result["page_count"] = data.get("pageCount", 1)
                return result
            return {"items": rows, "row_count": len(rows), "page_count": data.get("pageCount", 1)}

    async def _get_invoice_payload(self, invoice_id: int, company: str) -> dict[str, Any]:
        """Fetch one detailed invoice response from an allowlisted company."""
        base_url, headers = self._connection(company)
        async with (self.http_client or secure_http_client)(
            timeout=30,
            follow_redirects=True,
            allowed_redirect_hosts={"moja.superfaktura.sk"},
        ) as client:
            response = await client.get(
                f"{base_url}/invoices/view/{invoice_id}.json", headers=headers
            )
            response.raise_for_status()
            data = response.json()
        if not isinstance(data, dict):
            raise TypeError("SuperFaktura invoice response must be a mapping")
        return data

    async def get_invoice(
        self,
        invoice_id: int,
        company: str = "default",
        include_client: bool = False,
        include_notes: bool = False,
    ) -> dict:
        """Return a normalized invoice with optional client identity and free-text notes."""
        data = await self._get_invoice_payload(invoice_id, company)
        result: dict[str, Any] = self._invoice_record(data, company)
        result["items"] = self._invoice_items(data)
        if include_client:
            result["client"] = self._invoice_client(data)
        if include_notes:
            result["notes"] = self._invoice_notes(data)
        return result

    async def get_invoice_payments(self, invoice_id: int, company: str = "default") -> dict:
        """Return normalized payment information embedded in an invoice."""
        invoice = await self._get_invoice_payload(invoice_id, company)
        candidates = []
        for key in ("payments", "payment", "InvoicePayment", "invoice_payments"):
            value = invoice.get(key)
            if value:
                candidates.extend(value if isinstance(value, list) else [value])
        return self.limiter.limit([self._payment_record(item) for item in candidates])

    async def list_clients(
        self, company: str = "default", page: int = 1, include_contact: bool = False
    ) -> dict:
        """List normalized clients, omitting contact fields by default."""
        base_url, headers = self._connection(company)
        async with (self.http_client or secure_http_client)(
            timeout=30,
            follow_redirects=True,
            allowed_redirect_hosts={"moja.superfaktura.sk"},
        ) as client:
            response = await client.get(
                f"{base_url}/clients/index.json",
                headers=headers,
                params={"listinfo": 1, "per_page": 100, "page": max(page, 1)},
            )
            response.raise_for_status()
            data = response.json()
            rows = [self._client_record(item, include_contact) for item in data.get("items", [])]
            return {"items": rows, "row_count": len(rows), "page_count": data.get("pageCount", 1)}

    async def get_client(
        self, client_id: int, company: str = "default", include_contact: bool = False
    ) -> dict:
        """Return a normalized client, omitting contact fields by default."""
        base_url, headers = self._connection(company)
        async with (self.http_client or secure_http_client)(
            timeout=30,
            follow_redirects=True,
            allowed_redirect_hosts={"moja.superfaktura.sk"},
        ) as client:
            response = await client.get(
                f"{base_url}/clients/view/{client_id}.json", headers=headers
            )
            response.raise_for_status()
            data = response.json()
        if not isinstance(data, dict):
            raise TypeError("SuperFaktura client response must be a mapping")
        return self._client_record(data, include_contact)

    async def download_invoice_pdf(
        self, invoice_id: int, destination: str, language: str = "slo", company: str = "default"
    ) -> dict:
        """Download invoice pdf."""
        if language not in self.ALLOWED_LANGUAGES:
            raise ValueError("Unsupported invoice language")
        path = self.paths.resolve(destination, {".pdf"})
        base_url, headers = self._connection(company)
        async with (
            (self.http_client or secure_http_client)(
                timeout=60,
                follow_redirects=True,
                allowed_redirect_hosts={"moja.superfaktura.sk"},
            ) as client,
            client.stream(
                "GET", f"{base_url}/{language}/invoices/pdf/{invoice_id}", headers=headers
            ) as response,
        ):
            response.raise_for_status()
            if "application/pdf" not in response.headers.get("content-type", "").lower():
                raise RuntimeError("SuperFaktura did not return a PDF")
            size = await self.limiter.write_stream(
                response, path, self.settings.export_max_bytes("superfaktura")
            )
        return {"path": str(path.relative_to(self.settings.workspace)), "size": size}
