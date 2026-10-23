"""Compose the FastAPI application from vertical feature slices."""

from fastapi import FastAPI

from bootstrap.container import ApplicationContainer, build_container
from bootstrap.http import configure_http
from bootstrap.lifecycle import lifespan
from features.agents.api.router import router as health_router
from features.chat.api.router import router as conversations_router
from features.identity.api.router import router as sessions_router
from features.metabase_planning.api.router import router as metabase_planning_router
from features.workspace.api.admin_router import router as admin_router
from features.workspace.api.errors import configure_workspace_error_handlers
from features.workspace.api.user_router import router as workspace_router


def create_app(container: ApplicationContainer | None = None) -> FastAPI:
    """Build one API application with explicit infrastructure dependencies."""
    application = FastAPI(title="Open Agent Workspace", version="0.1.0", lifespan=lifespan)
    application.state.container = container or build_container()
    configure_http(application)
    configure_workspace_error_handlers(application)
    for router in (
        health_router,
        sessions_router,
        conversations_router,
        metabase_planning_router,
        workspace_router,
        admin_router,
    ):
        application.router.routes.extend(router.routes)
    return application


app = create_app()


def main() -> None:
    """Run the local backend entry point."""
    import uvicorn

    uvicorn.run(
        "bootstrap.app:app",
        host="127.0.0.1",
        port=18000,
        proxy_headers=True,
        forwarded_allow_ips="127.0.0.1",
        server_header=False,
    )
