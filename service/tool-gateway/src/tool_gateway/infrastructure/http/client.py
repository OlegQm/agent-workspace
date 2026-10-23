"""Construct outbound HTTP clients with redirect validation."""

import httpx

from tool_gateway.infrastructure.security.urls import require_https_url


class HttpClientFactory:
    """Create HTTP clients with the gateway's redirect policy."""

    def create(
        self,
        *,
        timeout: float | httpx.Timeout,
        follow_redirects: bool = False,
        allowed_redirect_hosts: set[str] | None = None,
        allow_redirect_subdomains: bool = False,
    ) -> httpx.AsyncClient:
        """Create a client that validates every followed redirect target."""
        return secure_http_client(
            timeout=timeout,
            follow_redirects=follow_redirects,
            allowed_redirect_hosts=allowed_redirect_hosts,
            allow_redirect_subdomains=allow_redirect_subdomains,
        )


def secure_http_client(
    *,
    timeout: float | httpx.Timeout,
    follow_redirects: bool = False,
    allowed_redirect_hosts: set[str] | None = None,
    allow_redirect_subdomains: bool = False,
) -> httpx.AsyncClient:
    """Create an HTTP client with bounded, host-validated redirects."""
    if follow_redirects and not allowed_redirect_hosts:
        raise ValueError("Redirect-following clients require an explicit host allowlist")

    async def validate_redirect(response: httpx.Response) -> None:
        """Reject a redirect before credentials reach an unapproved host."""
        if not response.is_redirect:
            return
        location = response.headers.get("location")
        if not location:
            raise ValueError("Redirect response has no Location header")
        destination = str(response.url.join(location))
        require_https_url(
            destination,
            allowed_hosts=allowed_redirect_hosts,
            allow_subdomains=allow_redirect_subdomains,
            label="Redirect destination",
        )

    return httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=follow_redirects,
        max_redirects=5,
        trust_env=False,
        event_hooks={"response": [validate_redirect]} if follow_redirects else None,
    )
