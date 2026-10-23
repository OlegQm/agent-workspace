"""Compose concrete infrastructure dependencies for the HTTP application."""

from collections.abc import Callable
from dataclasses import dataclass

from features.agents.infrastructure.configuration.models import AgentConfig
from features.agents.infrastructure.configuration.registry import AgentRegistry
from infrastructure.database.initialization import DatabaseInitializer
from infrastructure.database.session import SessionLocal
from infrastructure.database.session import engine as database_engine
from infrastructure.settings import Settings, settings


@dataclass
class ApplicationContainer:
    """Hold the application-owned infrastructure dependencies."""

    settings: Settings
    session_factory: object
    agent_loader: Callable[[], dict[str, AgentConfig]]
    database_initializer: DatabaseInitializer


def build_container() -> ApplicationContainer:
    """Build the production dependency container without external side effects."""
    return ApplicationContainer(
        settings=settings,
        session_factory=SessionLocal,
        agent_loader=AgentRegistry(settings).load,
        database_initializer=DatabaseInitializer(
            database_engine,
            allow_destructive_reset=settings.app_env != "production",
        ),
    )
