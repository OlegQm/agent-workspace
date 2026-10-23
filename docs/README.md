# Documentation

Start with the guide for your task, then read the README nearest the code you change.
Documentation is maintained in English alongside the implementation.

## Guides

- [Getting started](getting-started.md): prerequisites, one-agent setup, and platform limits.
- [Architecture](architecture.md): services, ownership, state, and dependency boundaries.
- [Configuration](configuration.md): manifests, providers, credentials, and review settings.
- [Operations](operations.md): restart, diagnostics, export/import, and deployment.
- [Security](security.md): authorization, isolation, file protection, and limitations.
- [Coding-agent instructions](../.agents/AGENTS.md): ownership, verification, and documentation review.

## Module Map

- [Backend](../service/backend/README.md): HTTP, accounts, chat, files, and planning.
- [Tool Gateway](../service/tool-gateway/README.md): role-scoped MCP integrations.
- [Frontend](../service/frontend/README.md): user/admin views and responsive UI.
- [Code Sync](../service/code-sync/README.md): read-only repository snapshots.
- [Infrastructure](../infra/README.md): Compose, nginx, and sandbox runtime.
- [Configuration files](../config/README.md): agents, source schemas, and repository policy.
- [Scripts](../scripts/README.md): lifecycle commands and local verification.
- [CI and deployment](../.github/workflows/README.md): workflow ownership and secret inventory.

Each module README links its smaller ownership areas and relevant tests.
Test trees mirror Python ownership; they do not repeat the module documentation.

## Documentation Boundaries

Guides explain cross-service tasks. Local README files explain module responsibilities,
entry points, dependencies, and tests. Source schemas and generated API/tool contracts
remain the detailed reference; Markdown must not duplicate every field or function.

The checker validates coverage, required sections, and local link targets, not the
truth of descriptions or heading fragments. Authors must review semantic accuracy.
External links are not requested by the checker.

The organization follows [GitHub README guidance](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-readmes),
[Diataxis](https://diataxis.fr/start-here/), and [Docs as Code](https://www.writethedocs.org/guide/docs-as-code/):
keep onboarding brief, separate guides from explanation/reference, and review docs with code.
