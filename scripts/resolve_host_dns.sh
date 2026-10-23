#!/usr/bin/env bash
set -Eeuo pipefail

python3 - <<'PY'
import ipaddress
import os
from pathlib import Path

configured = os.environ.get("TOOL_GATEWAY_DNS", "").strip()
if configured:
    candidates = [configured]
else:
    candidates = [
        fields[1]
        for line in Path("/etc/resolv.conf").read_text(encoding="utf-8").splitlines()
        if len(fields := line.split()) >= 2 and fields[0] == "nameserver"
    ]

for candidate in candidates:
    try:
        print(ipaddress.ip_address(candidate))
        break
    except ValueError:
        continue
else:
    raise SystemExit("No valid DNS resolver is configured for Tool Gateway")
PY
