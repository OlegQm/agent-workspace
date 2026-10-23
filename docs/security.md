# Security Boundaries

## Accounts and Requests

Opaque HttpOnly session cookies identify server-side sessions; the UI does not hold a
readable JWT. Activity refreshes expiry with a five-minute write throttle. A `401` clears
workspace state and returns to sign-in. Administrator authority comes from persisted
`is_admin`. Regular requests are scoped by both user and agent; admins cannot run agents.

FastAPI checks hosts and same-origin browser mutations. Production rejects mutations
without Origin/Referer. Declared and streamed request sizes are bounded; uploads have a
separate allowance. nginx restricts CSP/framing/sniffing, forwarded headers, connections,
and login/API rates. See [HTTP bootstrap](../service/backend/src/bootstrap/README.md).

## Processes, Credentials, and Network

Docker Sandboxes isolate agent execution and private working state. Source APIs are
mediated by agent-scoped gateways with manifest allowlists; empty scopes fail closed.
The host credential proxy replaces a sentinel only at the configured gateway endpoint.
Real gateway tokens must not be placed in agent workspaces.

Source credentials live in ignored protected runtime files. Backend, frontend, and
sandboxes do not receive gateway source payloads. Code Sync alone receives its Git token.
Host services have separate mount/network exposure: sandbox isolation does not imply
that every shared service can only see one agent directory. Review Compose mounts too.

Hermes/gateways remain private listeners. Internal HTTP clients disable ambient proxy
trust and redirects by default; source-specific external redirects have explicit checks.
Backend, gateways, and Code Sync drop capabilities and set no-new-privileges; nginx has
only the capability needed for its low port. Locks and base images pin build inputs.

The current sandbox policy allows general internet access. It is not DLP and cannot
prevent an agent from sending already-read information to an external site. Strict
protection needs an outbound allowlist, host firewalling, and source-side read-only grants.

## Files and Protected Content

Filesystem operations stay beneath the authenticated workspace and reject traversal,
unsafe symlinks, and root deletion. Protected paths can remain visible/previewable while
regular download, copy-path, modification, rename, and deletion are denied. Agent-readable
policy adds confidentiality instructions; derivative checks add bounded content safeguards.

These controls are not DRM. Visible content can be captured. Prompt instructions and
bounded overlap detection are not proofs of zero leakage. Read [workspace policies](../service/backend/src/features/workspace/README.md)
before changing access, preview, generated-artifact, or export behavior.

## Planning and External Writes

Metabase planning is regular-user only; admins can view marked conversations and export
them but cannot invoke planning/review actions. Files may explain expectations, formulas,
and implementation context; their values/claims are not authoritative chart data.
File content, paths, excerpts, secrets, and derivatives must not be sent to YouTrack.

Planning never builds a Question. The explicit confirmed review action may create/update
a linked YouTrack issue only when enabled and configured. Authorized safe navigation
uses configured HTTPS origins. [Planning documentation](../service/backend/src/features/metabase_planning/README.md)
describes revision, idempotency, and provenance checks; defaults remain fail-closed.
