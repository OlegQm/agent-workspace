"""Validate outbound HTTPS destinations."""

import ipaddress
from urllib.parse import urlsplit


def require_https_url(
    value: str,
    *,
    allowed_hosts: set[str] | None = None,
    allow_subdomains: bool = False,
    label: str = "URL",
) -> str:
    """Require an HTTPS URL without credentials or a nonstandard port."""
    parsed = urlsplit(str(value).strip())
    hostname = (parsed.hostname or "").rstrip(".").lower()
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError(f"{label} contains an invalid port") from exc
    if (
        parsed.scheme.lower() != "https"
        or not hostname
        or parsed.username
        or parsed.password
        or port not in {None, 443}
    ):
        raise ValueError(f"{label} must be a credential-free HTTPS URL on port 443")
    if allowed_hosts:
        normalized_hosts = {host.rstrip(".").lower() for host in allowed_hosts}
        accepted = hostname in normalized_hosts or (
            allow_subdomains and any(hostname.endswith(f".{host}") for host in normalized_hosts)
        )
        if not accepted:
            raise ValueError(f"{label} host is not allowed")
    return parsed.geturl()


def require_public_https_url(value: str, *, label: str = "URL") -> str:
    """Reject local or private literal destinations while requiring HTTPS."""
    normalized = require_https_url(value, label=label)
    hostname = (urlsplit(normalized).hostname or "").rstrip(".").lower()
    if hostname in {"localhost", "localhost.localdomain"} or hostname.endswith(
        (".localhost", ".local", ".internal")
    ):
        raise ValueError(f"{label} must not target a local host")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        if "." not in hostname:
            raise ValueError(f"{label} must use a public fully qualified host")
    else:
        if not address.is_global:
            raise ValueError(f"{label} must not target a private or local address")
    return normalized
