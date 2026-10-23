"""Test Tool Gateway dependency-container construction."""

from tool_gateway.bootstrap.container import build_container
from tool_gateway.infrastructure.configuration.settings import Settings


def test_build_container_injects_shared_dependencies_into_enabled_services() -> None:
    """Construct only manifest-enabled services from one settings instance."""
    configuration = Settings()
    container = build_container(configuration)

    assert container.settings is configuration
    assert set(container.services) == set(configuration.manifest.tools)
    assert container.audit.settings is configuration
    assert container.paths.settings is configuration
    assert container.exporter.settings is configuration
    assert container.exporter.paths is container.paths
    assert container.limiter.settings is configuration

    for service in container.services.values():
        assert service.client.settings is configuration
