# Coding-Agent Instructions

## Start with Ownership

Read the root [README](../README.md), [documentation index](../docs/README.md), and the
README nearest the code you will change. Follow each module's responsibilities,
dependencies, boundaries, and verification commands. Service and feature documentation
is in English and lives alongside its implementation. Runtime assistant prompts are not
repository contributor instructions.

## Required Documentation Review

After every change, review documentation for the affected modules and related workflows.
Update it when necessary. If no update is needed, state which documentation was reviewed
and why it remains accurate.

Behavior, contracts, configuration, commands, dependencies, security rules, or module
boundaries require corresponding documentation review in the same change. New logical
modules need local documentation and a link from their parent/module map. Do not create
duplicate sources of truth or formal no-op documentation edits.

## Implementation Boundaries

- Preserve unrelated work and keep edits within the requested scope.
- Keep Python imports absolute and respect the existing feature/integration layers.
- Read the relevant module documentation before changing its code.
- Use focused failing/green tests first for checker or behavior changes.
- Keep comments and documentation in English unless a user-facing locale explicitly requires otherwise.

## Verification

Run the applicable checks for the touched areas. The project-wide gates are:

```bash
task docs:check
task lint
task test
task deploy:validate
git diff --check
```

Python suites use fake external transports and disposable PostgreSQL; they do not need
working-source credentials. Browser tests use local fixtures. Do not provide production
credentials or a live application URL to local checks. Document unavailable prerequisites
instead of claiming skipped checks passed.

The docs checker validates module coverage, required sections, and local link targets. It
does not validate semantic accuracy or heading fragments and does not request external
URLs. Review the actual implementation and related user/operator documentation yourself.

## Safety and Completion

Never expose credentials, private logs, production data, or OAuth/session state. Do not run
deployment, authentication, data reset, or live integration operations just to verify
documentation. Never relax allowlists or expose listeners to make a local test pass.

On completion, report changed areas, checks and actual results, blockers, and the
documentation reviewed or updated. Pull-request authors should complete the repository's
PR checklist and describe any remaining risks without secrets.
