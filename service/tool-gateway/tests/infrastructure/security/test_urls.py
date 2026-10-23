"""Test outbound HTTPS destination validation."""

import pytest

from tool_gateway.infrastructure.security.urls import require_https_url, require_public_https_url


def test_require_https_url_rejects_unsafe_destinations() -> None:
    """Reject credentials, non-HTTPS schemes, ports, and unapproved hosts."""
    assert (
        require_https_url("https://api.example.com/path", allowed_hosts={"api.example.com"})
        == "https://api.example.com/path"
    )
    for value in (
        "http://api.example.com/path",
        "https://example-user:example-password@api.example.com/path",
        "https://api.example.com:444/path",
        "https://attacker.example/path",
        "https://api.example.com:not-a-port/path",
    ):
        with pytest.raises(ValueError):
            require_https_url(value, allowed_hosts={"api.example.com"})


def test_require_https_url_accepts_normalized_and_permitted_hosts() -> None:
    """Accept explicit hosts, trailing dots, and opted-in subdomains."""
    assert require_https_url(
        "https://API.EXAMPLE.COM./path", allowed_hosts={"api.example.com"}
    ) == "https://API.EXAMPLE.COM./path"
    assert require_https_url(
        "https://files.api.example.com/path",
        allowed_hosts={"api.example.com"},
        allow_subdomains=True,
    ) == "https://files.api.example.com/path"
    assert require_https_url("https://example.com/path") == "https://example.com/path"
    with pytest.raises(ValueError, match="host is not allowed"):
        require_https_url(
            "https://evil-example.com/path",
            allowed_hosts={"example.com"},
            allow_subdomains=True,
        )


def test_require_public_https_url_rejects_local_destinations() -> None:
    """Reject local names and private literal addresses."""
    for value in (
        "https://localhost/file",
        "https://service.internal/file",
        "https://127.0.0.1/file",
        "https://192.0.2.10/file",
    ):
        with pytest.raises(ValueError):
            require_public_https_url(value)


def test_require_public_https_url_accepts_public_destinations() -> None:
    """Accept public names and addresses while rejecting single-label names."""
    assert require_public_https_url("https://example.com/file") == "https://example.com/file"
    assert require_public_https_url("https://8.8.8.8/file") == "https://8.8.8.8/file"
    with pytest.raises(ValueError, match="fully qualified"):
        require_public_https_url("https://intranet/file")
