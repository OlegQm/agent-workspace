"""Test secure shared HTTP client construction."""

import httpx
import pytest

from tool_gateway.infrastructure.http.client import HttpClientFactory, secure_http_client


@pytest.mark.anyio
async def test_client_enforces_redirect_policy() -> None:
    """Validate redirect configuration and response hook behavior."""
    with pytest.raises(ValueError, match="allowlist"):
        secure_http_client(timeout=1, follow_redirects=True)

    client = secure_http_client(
        timeout=1,
        follow_redirects=True,
        allowed_redirect_hosts={"files.example.com"},
    )
    hook = client.event_hooks["response"][0]
    request = httpx.Request("GET", "https://files.example.com/start")
    await hook(httpx.Response(200, request=request))
    with pytest.raises(ValueError, match="no Location"):
        await hook(httpx.Response(302, request=request))
    await hook(httpx.Response(302, headers={"location": "/next"}, request=request))
    with pytest.raises(ValueError, match="host is not allowed"):
        await hook(
            httpx.Response(
                302,
                headers={"location": "https://attacker.example/file"},
                request=request,
            )
        )
    await client.aclose()

    plain = secure_http_client(timeout=httpx.Timeout(1))
    assert plain.event_hooks["response"] == []
    await plain.aclose()

    factory_client = HttpClientFactory().create(timeout=1)
    assert factory_client.event_hooks["response"] == []
    await factory_client.aclose()
