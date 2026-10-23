"""Wait for the local backend health endpoint without exposing response details."""

from __future__ import annotations

import argparse
import ipaddress
import json
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, build_opener


class RejectRedirects(HTTPRedirectHandler):
    """Keep the readiness request on its configured local endpoint."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        """Reject all redirects rather than following a potentially remote URL."""
        return


def local_health_url(value: str) -> bool:
    """Accept only an HTTP health URL on a numeric loopback address."""
    parsed = urlsplit(value)
    if (
        parsed.scheme != "http"
        or not parsed.hostname
        or parsed.username
        or parsed.password
    ):
        return False
    try:
        return ipaddress.ip_address(parsed.hostname).is_loopback
    except ValueError:
        return False


def wait_for_backend(url: str, timeout: float) -> bool:
    """Poll the local health route until it reports ready or the deadline expires."""
    opener = build_opener(ProxyHandler({}), RejectRedirects())
    deadline = time.monotonic() + timeout
    while True:
        try:
            with opener.open(
                url, timeout=min(2.0, max(deadline - time.monotonic(), 0.1))
            ) as response:
                payload = json.load(response)
                if (
                    response.status == 200
                    and isinstance(payload, dict)
                    and payload.get("status") == "ok"
                ):
                    return True
        except (HTTPError, OSError, URLError, ValueError, json.JSONDecodeError):
            pass
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False
        time.sleep(min(0.5, remaining))


def main() -> int:
    """Run the health wait command."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:18000/healthz")
    parser.add_argument("--timeout", type=float, default=60.0)
    args = parser.parse_args()
    if not local_health_url(args.url) or args.timeout < 0:
        print("Backend health check configuration is invalid", file=sys.stderr)
        return 2
    if wait_for_backend(args.url, args.timeout):
        print("Backend health check passed")
        return 0
    print("Backend health check failed before timeout", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
