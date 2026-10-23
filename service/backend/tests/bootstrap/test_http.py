"""Test backend HTTP boundary security helpers."""

import asyncio

from bootstrap.http import RequestBodyLimitMiddleware, header_origin, request_body_limit
from infrastructure.settings import settings


def test_header_origin_normalizes_valid_origins_and_referers() -> None:
    """Verify that same-origin checks compare origins rather than full paths."""
    assert header_origin("http://localhost/path?query=1") == "http://localhost"
    assert header_origin("not a URL") is None
    assert header_origin("javascript:alert(1)") is None


def test_only_upload_routes_receive_the_large_body_limit() -> None:
    """Verify that general JSON endpoints cannot use the file upload allowance."""
    assert request_body_limit("/api/files/upload") > settings.max_request_body_bytes
    assert request_body_limit("/api/admin/users/id/files/upload") > settings.max_request_body_bytes
    assert request_body_limit("/api/conversations") == settings.max_request_body_bytes


def test_backend_rejects_a_chunked_body_above_the_route_limit(monkeypatch) -> None:
    """Verify that omitted Content-Length does not bypass backend body limits."""
    monkeypatch.setattr(settings, "max_request_body_bytes", 5)
    sent: list[dict] = []
    chunks = [
        {"type": "http.request", "body": b"123", "more_body": True},
        {"type": "http.request", "body": b"456", "more_body": False},
    ]

    async def receive() -> dict:
        """Return the next body chunk."""
        return chunks.pop(0)

    async def send(message: dict) -> None:
        """Collect one response message."""
        sent.append(message)

    async def application(scope, receive_body, send_response) -> None:
        """Consume the bounded request body."""
        while True:
            message = await receive_body()
            if not message.get("more_body"):
                break
        await send_response({"type": "http.response.start", "status": 200, "headers": []})

    middleware = RequestBodyLimitMiddleware(application)
    asyncio.run(
        middleware(
            {"type": "http", "headers": [], "path": "/api/conversations"},
            receive,
            send,
        )
    )
    assert sent[0]["status"] == 413
