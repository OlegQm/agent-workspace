# Configuration

## Sources of Truth

- [Environment example](../.env.example): application/runtime setting names, never live secrets.
- [Agent manifests and schema](../config/agents/README.md): identities, ports, tools, resources, LLM profiles.
- [LLM overrides](../config/llm.env): versioned non-secret provider/model overrides.
- [Source credential example](../config/source-credentials.example.yaml): decoded credential shape.
- [Repository policy](../config/repositories.yaml): optional code snapshot aliases, URLs, and branches.
- [Production inventory](../.github/workflows/environment.md): protected GitHub Environment inputs.

Backend settings and gateway settings validate their own environment. Read the relevant
module README and schema before adding configuration; do not duplicate full field tables.

## Providers and Models

The example profiles select `openai-codex` with placeholder model IDs and a balanced
default mode. Replace those placeholders with model IDs supported by the selected
provider/runtime before starting an agent. The browser sends a mode, not an arbitrary
provider model identifier.
Manifest `llm` values provide the base profile. Global `LLM_*` overrides replace them;
agent-scoped names such as `LLM_ASSISTANT_MODEL_MEDIUM` take precedence over global values.

A provider switch requires coherent provider, API mode, auth method, three models, and
compression configuration. Validation rejects unsupported combinations. API-key profiles
name a credential environment variable; its value belongs only in ignored root `.env`.
Never put keys in manifests or `config/llm.env`. Provider support must be verified for
the pinned Hermes runtime before claiming a new provider works.

Apply changes with `task runtime:prepare`, restart affected agents, and recreate/restart
the backend with the updated environment. OAuth profiles use `task agent:auth`; API-key
profiles read their configured key during preparation. Existing OAuth/session state is
not intentionally replaced by configuration synchronization.

## Credentials and Scope

Assistant source credentials are a Base64 payload in ignored `.env`; Base64 is not encryption.
Preparation/start atomically render mode-`0600` files under `data/runtime-secrets`.
Source values go only to the relevant gateway; the code-read token goes to Code Sync.
Code Sync has no upstream repositories enabled by default. To enable code tools, add
repository aliases and branches to `config/repositories.yaml`, then add the same aliases
to the assistant manifest's `resources.code_repositories`. Aliases must start with a
lowercase letter and contain only lowercase letters, digits, underscores, or hyphens.
Only explicitly configured repositories are fetched; an empty inventory makes no network
requests. The current runtime-secret bundle still requires a GitHub token value even with
an empty inventory; it is not used until a GitHub upstream is configured. Scope it read-only
to the selected repositories.
The sandbox gateway token stays in the host store and is injected by the credential proxy.

Populate only explicitly authorized source credentials through the documented local environment workflow.
Rendering prunes duplicate per-source overrides; generated files are disposable. See
the [script tools](../scripts/README.md).
Credentials and authorization are separate: empty resource allowlists deny access.
Application PostgreSQL is separate from external BI sources; no database tunnel is provided.
The current manifest schema and gateway require `resources.environment: prod`. This is a
generic production-only source policy, not a company endpoint; supporting non-production
source environments requires a separate review of that access policy.

## Metabase Planning Review

Planning links and YouTrack writes are disabled by default. Enable them only after a
separately authorized preflight of the target service and permissions:

- Metabase links require the enable flag and a valid HTTPS `METABASE_PUBLIC_URL` origin.
- YouTrack requires its enable flag, HTTPS base origin, token, project ID, resolved user
  ID, and assignee custom-field ID. An email or visible field label is not the resolved ID.
- Confirm the field's user-assignment semantics and the token's create/update/comment/status
  permissions in the configured project. Never use a broad production write test implicitly.

Incomplete enabled settings fail validation. Keep external actions disabled for local
fake-based tests. [Planning](../service/backend/src/features/metabase_planning/README.md)
describes submission, provenance, status refresh, and secure navigation boundaries.
