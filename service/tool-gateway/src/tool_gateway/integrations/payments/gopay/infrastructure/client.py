"""Provide the read-only payment provider adapter."""

import asyncio
from collections.abc import Callable
from typing import Any

from tool_gateway.infrastructure.configuration.settings import Settings
from tool_gateway.infrastructure.http.client import secure_http_client
from tool_gateway.infrastructure.http.limits import ResultLimiter
from tool_gateway.infrastructure.security.credentials import require_config
from tool_gateway.infrastructure.security.resources import require_allowed_exact
from tool_gateway.infrastructure.security.urls import require_https_url


class GoPayClient:
    """Provide read-only operations for GoPay."""

    def __init__(
        self,
        settings: Settings,
        limiter: ResultLimiter | None = None,
        http_client: Callable[..., Any] | None = None,
    ) -> None:
        """Initialize the client with its role-scoped configuration."""
        self.settings = settings
        self.limiter = limiter or ResultLimiter(settings)
        self.http_client = http_client

    @staticmethod
    def _redact(value: dict) -> dict:
        """Handle internal redact details."""
        allowed = {
            "id",
            "state",
            "amount",
            "currency",
            "payment_instrument",
            "created_at",
            "paid_at",
            "recurrence",
            "parent_id",
            "lang",
            "target",
            "order_number",
        }
        return {key: item for key, item in value.items() if key in allowed}

    def _profile(self, alias: str) -> dict:
        """Handle internal profile details."""
        require_allowed_exact(
            alias, self.settings.manifest.resources.gopay_accounts, "GoPay account"
        )
        return self.settings.credential("gopay", alias)

    async def _token(self, profile: dict) -> str:
        """Handle internal token details."""
        base_url = require_https_url(
            str(profile.get("api_url", "https://gate.gopay.cz/api")),
            allowed_hosts={"gate.gopay.cz"},
            label="GoPay API URL",
        ).rstrip("/")
        async with (self.http_client or secure_http_client)(timeout=30) as client:
            response = await client.post(
                f"{base_url}/oauth2/token",
                auth=(
                    require_config(profile.get("client_id"), "GoPay client_id"),
                    require_config(profile.get("client_secret"), "GoPay client_secret"),
                ),
                data={"grant_type": "client_credentials", "scope": "payment-all"},
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
            return response.json()["access_token"]

    async def get_payment(self, account: str, payment_id: str) -> dict:
        """Return payment."""
        if not payment_id.isdigit():
            raise ValueError("GoPay payment_id must be numeric")
        profile = self._profile(account)
        token = await self._token(profile)
        return await self._get_payment(profile, token, payment_id)

    async def _get_payment(self, profile: dict, token: str, payment_id: str) -> dict:
        """Return payment."""
        base_url = require_https_url(
            str(profile.get("api_url", "https://gate.gopay.cz/api")),
            allowed_hosts={"gate.gopay.cz"},
            label="GoPay API URL",
        ).rstrip("/")
        async with (self.http_client or secure_http_client)(timeout=30) as client:
            response = await client.get(
                f"{base_url}/payments/payment/{payment_id}",
                headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            )
            response.raise_for_status()
            return self._redact(response.json())

    async def get_payments(self, account: str, payment_ids: list[str]) -> dict:
        """Return payments."""
        if not 1 <= len(payment_ids) <= 100:
            raise ValueError("GoPay batch requires between 1 and 100 payment IDs")
        if any(not item.isdigit() for item in payment_ids):
            raise ValueError("Every GoPay payment_id must be numeric")
        profile = self._profile(account)
        token = await self._token(profile)
        rows = await asyncio.gather(
            *(self._get_payment(profile, token, item) for item in payment_ids)
        )
        return self.limiter.limit(rows)
