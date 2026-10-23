"""Protect the MCP ASGI endpoint at the HTTP boundary."""

import hmac


class GatewayRequestBodyTooLarge(Exception):
    """Signal that an MCP request body exceeded its gateway limit."""


class BearerAuthMiddleware:
    """Enforce authentication, request limits, and safe response headers."""

    RESPONSE_HEADERS = (
        (b"cache-control", b"no-store, private"),
        (b"pragma", b"no-cache"),
        (b"x-content-type-options", b"nosniff"),
        (b"x-frame-options", b"DENY"),
        (b"referrer-policy", b"no-referrer"),
    )

    def __init__(self, app, token: str, max_request_body_bytes: int) -> None:
        """Initialize the middleware with its downstream ASGI application."""
        self.app = app
        self.expected = f"Bearer {token}".encode()
        self.max_request_body_bytes = max_request_body_bytes

    async def _reject(self, send, status: int, detail: bytes) -> None:
        """Return a bounded JSON error without invoking the MCP application."""
        headers = [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(detail)).encode()),
            *self.RESPONSE_HEADERS,
        ]
        await send({"type": "http.response.start", "status": status, "headers": headers})
        await send({"type": "http.response.body", "body": detail})

    async def __call__(self, scope, receive, send) -> None:
        """Handle one ASGI request."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request_headers = dict(scope.get("headers", []))
        supplied = request_headers.get(b"authorization", b"")
        if not hmac.compare_digest(supplied, self.expected):
            await self._reject(send, 401, b'{"detail":"Unauthorized"}')
            return
        content_length = request_headers.get(b"content-length")
        if content_length:
            try:
                parsed_length = int(content_length)
            except ValueError:
                await self._reject(send, 400, b'{"detail":"Invalid Content-Length"}')
                return
            if parsed_length < 0:
                await self._reject(send, 400, b'{"detail":"Invalid Content-Length"}')
                return
            if parsed_length > self.max_request_body_bytes:
                await self._reject(send, 413, b'{"detail":"Request body is too large"}')
                return

        received = 0

        async def bounded_receive():
            """Count streamed request bytes before MCP request parsing."""
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_request_body_bytes:
                    raise GatewayRequestBodyTooLarge
            return message

        async def secure_send(message) -> None:
            """Append gateway security headers to every HTTP response."""
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                existing = {name.lower() for name, _ in headers}
                headers.extend(
                    header for header in self.RESPONSE_HEADERS if header[0] not in existing
                )
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, bounded_receive, secure_send)
        except GatewayRequestBodyTooLarge:
            await self._reject(send, 413, b'{"detail":"Request body is too large"}')
