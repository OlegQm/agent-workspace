"""Configure the test environment and shared fixtures."""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
os.environ["GATEWAY_ROLE"] = "assistant"
os.environ["GATEWAY_PORT"] = "18765"
os.environ["GATEWAY_TOKEN_ENV"] = "TOOL_GATEWAY_TOKEN_ASSISTANT"
os.environ["TOOL_GATEWAY_TOKEN_ASSISTANT"] = "test-token-at-least-32-characters"
os.environ["AGENT_CONFIG_DIR"] = str(ROOT / "config/agents")
os.environ["AGENT_DATA_DIR"] = str(ROOT / "data/agents")
os.environ["CODE_CONFIG_FILE"] = str(ROOT / "config/repositories.yaml")
