# Workspace Confidentiality

## Purpose

Detect bounded restricted-source reproduction in messages and generated artifacts.
These safeguards complement path policy; they are not a general DLP proof.

## Responsibilities

- Build ephemeral hashes/text fingerprints from protected source files.
- Check exact copies, archives, excerpt windows, and substantial textual overlap.
- Remove generated derivatives and sanitize sensitive links/payload strings.

## Entry Points

- [RestrictedContentGuard and cache](guard.py)
- [Fingerprint/result records](models.py)
- [Bounded extraction and normalization](normalization.py)

## Dependencies and Boundaries

File-size/source-count limits bound work; unsupported or unreadable formats have
limited enforcement. Stable workspace signatures and locks protect the decision cache.
Do not describe prompt policy, visible preview restrictions, or overlap checks as DRM.

## Tests

`tests/features/workspace/infrastructure/confidentiality` covers models, extraction,
limits, archive errors, overlap decisions, cache races, sanitization, and deletion.
Use synthetic documents, never restricted business files.

## Related Documentation

- [Workspace policy](../../README.md)
- [Protection limits](../../../../../../../docs/security.md)
