# Payment Integrations

## Purpose

Group independent read-only GoPay and Stripe adapters.
This namespace does not implement a shared payment workflow.

## Responsibilities

- Keep each provider's tools, service, client, credentials, and tests separate.
- Register only the provider tools enabled by the agent manifest.
- Preserve source-side least privilege in addition to gateway allowlists.

## Entry Points

- [GoPay](gopay/README.md)
- [Stripe](stripe/README.md)
- [Provider selection](../../bootstrap/container.py)

## Dependencies and Boundaries

Cross-provider imports should not introduce shared mutable state or broaden authority.
The common payments namespace is an architecture exception for organization, not a
permission to invoke writes. The bundled assistant includes read-only payment tools, but
empty account allowlists and absent source credentials keep access closed by default.

## Tests

`tests/integrations/payments` mirrors the two providers. Bootstrap contracts verify the
manifest-selected tool set. Tests never use provider credentials or real payment IDs.

## Related Documentation

- [Gateway map](../../../../README.md)
- [Security](../../../../../../docs/security.md)
