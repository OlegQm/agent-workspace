"""Load and validate configured Open Agent Workspace agent manifests."""

import os
from dataclasses import dataclass
from functools import lru_cache

import yaml

from features.agents.infrastructure.configuration.llm import profile_from_environment
from features.agents.infrastructure.configuration.models import AgentConfig
from infrastructure.settings import Settings, settings


@dataclass(frozen=True)
class AgentRegistry:
    """Load and validate all agents from one configured manifest directory."""

    settings: Settings

    def load(self) -> dict[str, AgentConfig]:
        """Load all configured agents while enforcing cross-manifest uniqueness."""
        agents: dict[str, AgentConfig] = {}
        sandboxes: set[str] = set()
        allocated_ports: set[int] = set()
        for path in sorted(self.settings.agent_config_dir.glob("*.yaml")):
            values = yaml.safe_load(path.read_text())
            values["llm"] = profile_from_environment(values["llm"], values["id"], os.environ)
            config = AgentConfig.model_validate(values)
            if config.id in agents:
                raise RuntimeError(f"duplicate agent id: {config.id}")
            if config.sandbox_name in sandboxes:
                raise RuntimeError(f"duplicate sandbox name: {config.sandbox_name}")
            requested_ports = {config.host_port, config.tool_gateway_port}
            if len(requested_ports) != 2 or requested_ports & allocated_ports:
                raise RuntimeError(f"agent {config.id} reuses a Hermes or Tool Gateway port")
            agents[config.id] = config
            sandboxes.add(config.sandbox_name)
            allocated_ports.update(requested_ports)
        if not agents:
            raise RuntimeError(f"no agent manifests in {self.settings.agent_config_dir}")
        return agents

    def get(self, agent_id: str, agents: dict[str, AgentConfig]) -> AgentConfig:
        """Return one agent from an already validated registry snapshot."""
        try:
            return agents[agent_id]
        except KeyError as exc:
            raise LookupError(f"unknown agent: {agent_id}") from exc


@lru_cache(maxsize=1)
def load_agents() -> dict[str, AgentConfig]:
    """Return the cached default agent registry snapshot."""
    return AgentRegistry(settings).load()


def get_agent(agent_id: str) -> AgentConfig:
    """Return one agent from the cached default registry snapshot."""
    return AgentRegistry(settings).get(agent_id, load_agents())
