"""Characterize DNS settings for the deployed Tool Gateway services."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[5]
COMPOSE_PATH = ROOT / "infra/orchestration/docker-compose/docker-compose.yml"
DNS_SETTING = "${TOOL_GATEWAY_DNS:-1.1.1.1}"


def test_tool_gateways_use_host_discovered_dns_without_changing_network_mode() -> None:
    """Keep both gateways on the host network while using its DNS resolver."""
    compose = yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))

    for service_name in ("tool-gateway-assistant",):
        service = compose["services"][service_name]

        assert service["network_mode"] == "host"
        assert service["dns"] == [DNS_SETTING]
