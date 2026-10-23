# Backend Bootstrap

## Purpose

Compose the FastAPI application and injected dependencies.
Keep lifecycle and HTTP-wide behavior outside individual features.

## Responsibilities

- Build the app/container and attach feature routers.
- Initialize database state and recover runtime tasks on startup.
- Apply host/origin checks, streamed body limits, and session refresh wiring.

## Entry Points

- [create_app / main](app.py)
- [ApplicationContainer](container.py)
- [HTTP-wide guards](http.py)
- [Startup and shutdown](lifecycle.py)

## Dependencies and Boundaries

Bootstrap may compose concrete adapters; feature packages must not import it.
Settings and database initialization are injected. App import is not a substitute for
running lifespan. Avoid network/database effects in dependency construction.

## Tests

`tests/bootstrap` covers factories, container, middleware, lifecycle, and composition.
Composition tests are intentionally cross-feature; other tests mirror individual modules.
Use the disposable PostgreSQL fixture, never a working application database.

## Related Documentation

- [Backend map](../../README.md)
- [Architecture](../../../../docs/architecture.md)
