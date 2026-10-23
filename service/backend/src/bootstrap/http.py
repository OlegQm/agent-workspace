"""Configure HTTP request boundaries and response security protections."""

from urllib.parse import urlsplit

from fastapi import Request, Response, status
from starlette.middleware.gzip import GZipMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from features.identity.api.cookies import clear_session_cookie
from infrastructure.settings import settings

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Permissions-Policy": (
        "camera=(), microphone=(), geolocation=(), payment=(), usb=(), "
        "fullscreen=(self), clipboard-write=(self)"
    ),
}


def header_origin(value: str | None) -> str | None:
    """Extract a normalized HTTP origin from an Origin or Referer header."""
    if not value:
        return None
    try:
        parsed = urlsplit(value)
    except ValueError:
        return None
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return f"{parsed.scheme}://{parsed.netloc}".rstrip("/")


def request_body_limit(path: str) -> int:
    """Return the accepted request body size for one API path."""
    if path == "/api/files/upload" or (
        path.startswith("/api/admin/users/") and path.endswith("/files/upload")
    ):
        return settings.max_upload_bytes + 1_048_576
    return settings.max_request_body_bytes


class RequestBodyLimitMiddleware:
    """Reject declared and streamed request bodies that exceed route limits."""

    def __init__(self, application) -> None:
        """Store the wrapped ASGI application."""
        self.application = application

    async def __call__(self, scope, receive, send) -> None:
        """Enforce the configured byte limit before request parsing."""
        if scope["type"] != "http":
            await self.application(scope, receive, send)
            return
        limit = request_body_limit(str(scope.get("path", "")))
        headers = dict(scope.get("headers", []))
        content_length = headers.get(b"content-length")
        if content_length:
            try:
                parsed_length = int(content_length)
            except ValueError:
                await self._reject(send, 400, b'{"detail":"Invalid Content-Length"}')
                return
            if parsed_length < 0:
                await self._reject(send, 400, b'{"detail":"Invalid Content-Length"}')
                return
            if parsed_length > limit:
                await self._reject(send, 413, b'{"detail":"Request body is too large"}')
                return

        received = 0

        async def bounded_receive():
            """Count streamed request bytes before passing them downstream."""
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise RequestBodyTooLarge
            return message

        try:
            await self.application(scope, bounded_receive, send)
        except RequestBodyTooLarge:
            await self._reject(send, 413, b'{"detail":"Request body is too large"}')

    @staticmethod
    async def _reject(send, response_status: int, body: bytes) -> None:
        """Return a small JSON rejection from the ASGI boundary."""
        await send(
            {
                "type": "http.response.start",
                "status": response_status,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                    (b"cache-control", b"no-store, private"),
                    (b"x-content-type-options", b"nosniff"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})


class RequestBodyTooLarge(Exception):
    """Signal that a streamed HTTP request exceeded its configured limit."""


async def origin_guard(request: Request, call_next):
    """Enforce same-origin mutations, bounded bodies, and safe response headers."""
    if request.method in UNSAFE_METHODS and request.url.path.startswith("/api/"):
        supplied_origin = header_origin(request.headers.get("origin"))
        supplied_referer = header_origin(request.headers.get("referer"))
        request_origin = supplied_origin or supplied_referer
        if request_origin and request_origin not in settings.allowed_origins:
            return Response(status_code=status.HTTP_403_FORBIDDEN)
        if settings.app_env == "production" and request_origin is None:
            return Response(status_code=status.HTTP_403_FORBIDDEN)

    response = await call_next(request)
    if response.status_code == status.HTTP_401_UNAUTHORIZED:
        clear_session_cookie(response)
    for header, value in SECURITY_HEADERS.items():
        response.headers.setdefault(header, value)
    if request.url.path.startswith("/api/") and request.url.path not in {
        "/api/files/preview",
        "/api/files/preview/pdf-page",
    }:
        response.headers.setdefault("Cache-Control", "no-store, private")
        response.headers.setdefault("Pragma", "no-cache")
    return response


def configure_http(application) -> None:
    """Attach the ordered security middleware stack to the composed application."""
    application.add_middleware(GZipMiddleware, minimum_size=1_024, compresslevel=5)
    application.add_middleware(TrustedHostMiddleware, allowed_hosts=sorted(settings.allowed_hosts))
    application.add_middleware(RequestBodyLimitMiddleware)
    application.middleware("http")(origin_guard)
