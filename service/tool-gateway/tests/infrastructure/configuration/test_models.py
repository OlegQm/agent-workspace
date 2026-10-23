"""Test manifests behavior."""

import json
from pathlib import Path

import jsonschema
import pytest
import yaml
from pydantic import ValidationError

from tool_gateway.infrastructure.configuration.models import Manifest

ROOT = Path(__file__).resolve().parents[5]


def test_agent_manifests_match_schema() -> None:
    """Verify that agent manifests match schema."""
    schema = json.loads((ROOT / "config/agents/schema.json").read_text())
    repository_item = schema["properties"]["resources"]["properties"]["code_repositories"][
        "items"
    ]
    assert repository_item["pattern"] == "^[a-z][a-z0-9_-]{0,63}$"
    assert yaml.safe_load((ROOT / "config/repositories.yaml").read_text()) == {
        "repositories": {}
    }
    for name in ("assistant",):
        manifest = yaml.safe_load((ROOT / f"config/agents/{name}.yaml").read_text())
        jsonschema.validate(manifest, schema)
        manifest["resources"]["code_repositories"] = ["my-project"]
        jsonschema.validate(manifest, schema)


def test_gateway_manifest_rejects_unsafe_repository_alias() -> None:
    """Repository aliases must not escape the configured snapshot directory."""
    manifest = yaml.safe_load((ROOT / "config/agents/assistant.yaml").read_text())
    manifest["resources"]["code_repositories"] = ["../outside"]

    with pytest.raises(ValidationError):
        Manifest.model_validate(manifest)
