# Frontend

## Purpose

Provide the responsive Vue workspace for ordinary users and administrators.
The backend remains authoritative for identity, run state, and planning actions.

## Responsibilities

- Compose login, chat, files, tool catalog, and read-only admin history views.
- Stream/reconnect run events and reflect validated planning state.
- Localize user-facing text in English and Slovak; agent replies follow the user's language.

## Entry Points

- [Browser entrypoint](src/main.ts)
- [Top-level composition](src/App.vue)
- [HTTP/SSE contracts](src/api.ts)
- [Translations](src/i18n.ts)
- [Development and verification commands](package.json)

## Dependencies and Boundaries

Run `npm --prefix service/frontend run dev` for local development; Vite proxies APIs
according to its configuration. The production image builds assets and serves nginx.
Vue/TypeScript own the UI; Radix/Lucide and Tailwind support controls, Markdown-It and
DOMPurify render sanitized message content. Dependency versions live in the lockfile.
The API client uses session cookies, handles unauthorized responses, and does not store
provider/source secrets. Do not infer permissions or workflow transitions from prose.

## Tests

Run `npm --prefix service/frontend run typecheck`, `run test`, and `run test:e2e`.
Playwright checks desktop/mobile with fake API transport by default. A real host URL
is an explicit operator choice, not part of ordinary local verification.

## Related Documentation

- [auth](src/components/auth/README.md)
- [chat](src/components/chat/README.md)
- [layout](src/components/layout/README.md)
- [files](src/components/files/README.md)
- [admin](src/components/admin/README.md)
- [common](src/components/common/README.md)
- [tools](src/components/tools/README.md)
- [Metabase planning](src/features/metabase-planning/README.md)
- [Workspace orchestration](src/composables/README.md)
- [Shared helpers](src/lib/README.md)
- [Architecture](../../docs/architecture.md)
- [Coding-agent and repository guidance](../../.agents/AGENTS.md)
