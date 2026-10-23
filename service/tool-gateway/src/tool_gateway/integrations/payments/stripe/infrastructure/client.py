"""Provide the read-only Stripe client."""

from collections.abc import Callable
from typing import Any, ClassVar

from tool_gateway.infrastructure.configuration.settings import Settings
from tool_gateway.infrastructure.http.client import secure_http_client
from tool_gateway.infrastructure.security.credentials import require_config
from tool_gateway.infrastructure.security.resources import require_allowed_exact


class StripeClient:
    """Provide read-only operations for Stripe."""

    def __init__(
        self,
        settings: Settings,
        http_client: Callable[..., Any] | None = None,
    ) -> None:
        """Initialize the client with its role-scoped configuration."""
        self.settings = settings
        self.http_client = http_client

    ALLOWED_STATUSES: ClassVar[set[str]] = {
        "requires_payment_method",
        "requires_confirmation",
        "requires_action",
        "processing",
        "requires_capture",
        "canceled",
        "succeeded",
    }

    def _profile(self, alias: str) -> dict:
        """Return credentials for an allowlisted Stripe account."""
        require_allowed_exact(
            alias, self.settings.manifest.resources.stripe_accounts, "Stripe account"
        )
        return self.settings.credential("stripe", alias)

    async def _get(self, account: str, path: str, params: dict | None = None) -> dict:
        """Perform one authenticated read-only Stripe request."""
        profile = self._profile(account)
        key = require_config(profile.get("restricted_key"), f"Stripe {account} restricted key")
        headers = {"Authorization": f"Bearer {key}"}
        if profile.get("stripe_account"):
            headers["Stripe-Account"] = profile["stripe_account"]
        async with (self.http_client or secure_http_client)(timeout=30) as client:
            response = await client.get(
                f"https://api.stripe.com/v1/{path}", headers=headers, params=params
            )
            response.raise_for_status()
            return self._redact(response.json())

    @classmethod
    def _redact(cls, value):
        """Remove customer and other non-allowlisted response fields recursively."""
        allowed = {
            "amount",
            "amount_received",
            "amount_refunded",
            "balance_transaction",
            "charge",
            "created",
            "currency",
            "data",
            "fee",
            "has_more",
            "id",
            "livemode",
            "net",
            "object",
            "payment_intent",
            "refunded",
            "status",
            "type",
        }
        if isinstance(value, list):
            return [cls._redact(item) for item in value]
        if isinstance(value, dict):
            return {key: cls._redact(item) for key, item in value.items() if key in allowed}
        return value

    async def list_objects(
        self,
        account: str,
        object_type: str,
        created_from: int | None = None,
        created_to: int | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> dict:
        """List bounded PaymentIntents, Charges, or Refunds."""
        paths = {
            "payment_intents": "payment_intents",
            "charges": "charges",
            "refunds": "refunds",
        }
        if object_type not in paths:
            raise ValueError("Unsupported Stripe object type")
        if status and (object_type != "payment_intents" or status not in self.ALLOWED_STATUSES):
            raise ValueError("Unsupported Stripe status filter")
        params: dict[str, object] = {"limit": min(max(limit, 1), 100)}
        if created_from:
            params["created[gte]"] = created_from
        if created_to:
            params["created[lte]"] = created_to
        if status:
            params["status"] = status
        return await self._get(account, paths[object_type], params)

    async def get_object(self, account: str, object_type: str, object_id: str) -> dict:
        """Return one allowlisted Stripe payment object."""
        prefixes = {
            "payment_intents": "pi_",
            "charges": "ch_",
            "refunds": "re_",
            "balance_transactions": "txn_",
        }
        if object_type not in prefixes or not object_id.startswith(prefixes[object_type]):
            raise ValueError("Invalid Stripe object ID")
        return await self._get(account, f"{object_type}/{object_id}")
