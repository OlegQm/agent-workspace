"""Render or inspect one agent's Hermes configuration from its manifest."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import yaml
from features.agents.infrastructure.configuration.hermes import render_hermes_config
from features.agents.infrastructure.configuration.llm import profile_from_environment


def main() -> None:
    """Render a validated, non-secret Hermes configuration or inspect its profile."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--template", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--workspace")
    parser.add_argument("--tool-gateway-port")
    parser.add_argument("--field", choices=("provider", "auth_method", "credential_env"))
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    manifest = yaml.safe_load(args.manifest.read_text(encoding="utf-8"))
    profile = profile_from_environment(manifest["llm"], manifest["id"], os.environ)
    if args.field:
        print(getattr(profile, args.field) or "")
        return
    if args.template is None:
        parser.error("--template is required when rendering or checking")
    content = args.template.read_text(encoding="utf-8")
    substitutions = {
        "__AGENT_ID__": manifest["id"],
        "__WORKSPACE__": args.workspace or "/workspace",
        "__TOOL_GATEWAY_PORT__": args.tool_gateway_port or str(manifest["tool_gateway_port"]),
    }
    for source, replacement in substitutions.items():
        content = content.replace(source, replacement)
    result = render_hermes_config(yaml.safe_load(content), profile)
    if args.check:
        return
    if args.output is None or args.workspace is None:
        parser.error("--output and --workspace are required when writing")
    args.output.write_text(yaml.safe_dump(result, sort_keys=False), encoding="utf-8")


if __name__ == "__main__":
    main()
