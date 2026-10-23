"""Test application dependency-container construction."""

from types import SimpleNamespace

import pytest

from bootstrap import container


@pytest.mark.unit
def test_build_container_wires_default_infrastructure(monkeypatch: pytest.MonkeyPatch) -> None:
    """Construct production dependencies without triggering their external side effects."""
    settings = SimpleNamespace(name="settings", app_env="development")
    session_factory = object()
    engine = object()
    loader = object()
    initializer = object()

    class FakeRegistry:
        """Expose one stable loader bound to supplied settings."""

        def __init__(self, value: object) -> None:
            """Verify registry configuration."""
            assert value is settings
            self.load = loader

    def fake_initializer(value: object, *, allow_destructive_reset: bool) -> object:
        """Verify initializer engine injection."""
        assert value is engine
        assert allow_destructive_reset is True
        return initializer

    monkeypatch.setattr(container, "settings", settings)
    monkeypatch.setattr(container, "SessionLocal", session_factory)
    monkeypatch.setattr(container, "database_engine", engine)
    monkeypatch.setattr(container, "AgentRegistry", FakeRegistry)
    monkeypatch.setattr(container, "DatabaseInitializer", fake_initializer)

    result = container.build_container()
    assert result.settings is settings
    assert result.session_factory is session_factory
    assert result.agent_loader is loader
    assert result.database_initializer is initializer
