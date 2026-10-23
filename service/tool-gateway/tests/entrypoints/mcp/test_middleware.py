"""Test Tool Gateway HTTP boundary protections."""

import asyncio

from tool_gateway.entrypoints.mcp.middleware import BearerAuthMiddleware


def invoke_gateway(headers: list[tuple[bytes, bytes]], chunks: list[bytes]) -> list[dict]:
    """Invoke a minimal authenticated gateway request and collect ASGI messages."""
    sent: list[dict] = []
    pending = [
        {
            "type": "http.request",
            "body": chunk,
            "more_body": index < len(chunks) - 1,
        }
        for index, chunk in enumerate(chunks)
    ] or [{"type": "http.request", "body": b"", "more_body": False}]

    async def receive() -> dict:
        """Return the next request body chunk."""
        return pending.pop(0)

    async def send(message: dict) -> None:
        """Collect one response message."""
        sent.append(message)

    async def application(scope, receive_body, send_response) -> None:
        """Consume the request and emit a successful response."""
        while True:
            message = await receive_body()
            if not message.get("more_body"):
                break
        await send_response({"type": "http.response.start", "status": 200, "headers": []})
        await send_response({"type": "http.response.body", "body": b"ok"})

    middleware = BearerAuthMiddleware(application, "secret-token", 5)
    asyncio.run(
        middleware(
            {"type": "http", "headers": headers, "path": "/mcp", "method": "POST"},
            receive,
            send,
        )
    )
    return sent


def invoke_middleware(
    scope: dict,
    messages: list[dict],
    *,
    response_headers: list[tuple[bytes, bytes]] | None = None,
) -> tuple[list[dict], list[dict]]:
    """Invoke middleware and return sent messages plus downstream scopes."""
    sent: list[dict] = []
    downstream: list[dict] = []

    async def receive() -> dict:
        """Return the next ASGI message."""
        return messages.pop(0)

    async def send(message: dict) -> None:
        """Collect an ASGI response."""
        sent.append(message)

    async def application(inner_scope, inner_receive, inner_send) -> None:
        """Consume one message and return a response."""
        downstream.append(inner_scope)
        await inner_receive()
        await inner_send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": response_headers or [],
            }
        )

    boundary = BearerAuthMiddleware(application, "token", 5)
    asyncio.run(boundary(scope, receive, send))
    return sent, downstream


def test_gateway_requires_bearer_authentication() -> None:
    """Verify that unauthenticated requests fail before reaching MCP."""
    response = invoke_gateway([], [b""])
    assert response[0]["status"] == 401


def test_gateway_rejects_declared_and_streamed_oversized_bodies() -> None:
    """Verify that both Content-Length and chunked bodies are bounded."""
    authorization = (b"authorization", b"Bearer secret-token")
    declared = invoke_gateway([authorization, (b"content-length", b"6")], [b""])
    streamed = invoke_gateway([authorization], [b"123", b"456"])
    assert declared[0]["status"] == 413
    assert streamed[0]["status"] == 413


def test_gateway_adds_non_cacheable_security_headers() -> None:
    """Verify that successful MCP responses cannot be cached or framed."""
    response = invoke_gateway(
        [(b"authorization", b"Bearer secret-token"), (b"content-length", b"2")],
        [b"ok"],
    )
    headers = dict(response[0]["headers"])
    assert response[0]["status"] == 200
    assert headers[b"cache-control"] == b"no-store, private"
    assert headers[b"x-frame-options"] == b"DENY"


def test_non_http_invalid_lengths_and_existing_headers() -> None:
    """Characterize passthrough, malformed lengths, and existing response headers."""
    sent, downstream = invoke_middleware(
        {"type": "websocket"},
        [{"type": "websocket.receive"}],
    )
    assert sent[0]["status"] == 200 and downstream

    authorization = (b"authorization", b"Bearer token")
    for value in (b"invalid", b"-1"):
        sent, _ = invoke_middleware(
            {"type": "http", "headers": [authorization, (b"content-length", value)]},
            [{"type": "http.request", "body": b""}],
        )
        assert sent[0]["status"] == 400

    sent, _ = invoke_middleware(
        {"type": "http", "headers": [authorization]},
        [{"type": "http.disconnect"}],
        response_headers=[(b"cache-control", b"existing")],
    )
    assert sent[0]["headers"].count((b"cache-control", b"existing")) == 1
