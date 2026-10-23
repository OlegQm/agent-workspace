"""Test FastAPI application composition."""

from types import SimpleNamespace

import pytest

from bootstrap import app as application


@pytest.mark.unit
def test_create_app_uses_injected_container_and_registers_feature_routes() -> None:
    """Compose the HTTP application around an explicitly supplied container."""
    container = SimpleNamespace()
    app = application.create_app(container)

    assert app.state.container is container
    paths = {route.path for route in app.routes}
    assert "/healthz" in paths
    assert "/api/auth/login" in paths
    assert "/api/conversations" in paths
    assert "/api/files" in paths
    assert "/api/admin/users" in paths


@pytest.mark.unit
def test_main_starts_local_uvicorn_with_fixed_security_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Preserve the fixed loopback Uvicorn entrypoint contract."""
    received: dict[str, object] = {}
    import uvicorn

    monkeypatch.setattr(
        uvicorn,
        "run",
        lambda *args, **kwargs: received.update(args=args, kwargs=kwargs),
    )
    application.main()

    assert received["args"] == ("bootstrap.app:app",)
    assert received["kwargs"] == {
        "host": "127.0.0.1",
        "port": 18000,
        "proxy_headers": True,
        "forwarded_allow_ips": "127.0.0.1",
        "server_header": False,
    }
