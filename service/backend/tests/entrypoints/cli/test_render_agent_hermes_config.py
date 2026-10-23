"""Test the agent Hermes configuration renderer at its command boundary."""

import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[5]
SCRIPT = ROOT / "scripts/render_agent_hermes_config.py"
MANIFEST = ROOT / "config/agents/assistant.yaml"
TEMPLATE = ROOT / "infra/sandbox/hermes-config.template.yaml"


@pytest.mark.unit
def test_renderer_applies_agent_profile_to_hermes_config(tmp_path: Path) -> None:
    """Render the same non-secret provider profile used by the backend."""
    output = tmp_path / "config.yaml"
    environment = {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONPATH": str(ROOT / "service/backend/src"),
        "LLM_ASSISTANT_PROVIDER": "example-provider",
        "LLM_ASSISTANT_API_MODE": "chat_completions",
        "LLM_ASSISTANT_AUTH_METHOD": "api_key",
        "LLM_ASSISTANT_CREDENTIAL_ENV": "EXAMPLE_API_KEY",
        "LLM_ASSISTANT_NATIVE_COMPACTION": "false",
        "LLM_ASSISTANT_MODEL_SMALL": "example-small",
        "LLM_ASSISTANT_MODEL_MEDIUM": "example-medium",
        "LLM_ASSISTANT_MODEL_HIGH": "example-high",
        "LLM_ASSISTANT_DEFAULT_MODE": "high",
    }
    subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--manifest",
            str(MANIFEST),
            "--template",
            str(TEMPLATE),
            "--output",
            str(output),
            "--workspace",
            "/workspace",
            "--tool-gateway-port",
            "18765",
        ],
        check=True,
        env=environment,
        capture_output=True,
        text=True,
    )
    config = yaml.safe_load(output.read_text(encoding="utf-8"))
    assert config["model"] == {
        "default": "example-high",
        "provider": "example-provider",
        "api_mode": "chat_completions",
    }
    assert config["compression"] == {"enabled": True, "in_place": True}
    assert config["terminal"]["cwd"] == "/workspace"
    assert config["mcp_servers"]["open-agent-workspace"]["url"].endswith(":18765/mcp")


@pytest.mark.unit
def test_renderer_rejects_an_incomplete_provider_switch(tmp_path: Path) -> None:
    """Fail before writing a Hermes configuration for incompatible overrides."""
    output = tmp_path / "config.yaml"
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--manifest",
            str(MANIFEST),
            "--template",
            str(TEMPLATE),
            "--output",
            str(output),
            "--workspace",
            "/workspace",
        ],
        check=False,
        env={
            "PATH": os.environ.get("PATH", ""),
            "PYTHONPATH": str(ROOT / "service/backend/src"),
            "LLM_ASSISTANT_PROVIDER": "example-provider",
        },
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert not output.exists()
