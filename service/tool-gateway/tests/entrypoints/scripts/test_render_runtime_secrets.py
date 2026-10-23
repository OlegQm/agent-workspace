"""Test runtime secrets behavior."""

import importlib.util
import json
import stat
from pathlib import Path

SCRIPT = Path(__file__).parents[5] / "scripts/render_runtime_secrets.py"
SPEC = importlib.util.spec_from_file_location("render_runtime_secrets", SCRIPT)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def test_runtime_secrets_round_trip(tmp_path: Path) -> None:
    """Verify that runtime secrets round trip."""
    source = tmp_path / "source"
    source.mkdir()
    expected = {
        "assistant-sources.yaml": b"metabase:\n  default:\n    api_key: placeholder\n",
        "google-service-account.json": json.dumps(
            {
                "type": "service_account",
                "project_id": "project",
                "private_key": "private-key",
                "client_email": "user@example.invalid",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        ).encode(),
        "github-read-token": b"token\n",
    }
    for filename, content in expected.items():
        (source / filename).write_bytes(content)

    env_path = tmp_path / ".env"
    env_path.write_text("APP_ENV=test\n")
    module.capture(env_path, source)

    output = tmp_path / "runtime"
    module.render(env_path, output)

    assert {path.name: path.read_bytes() for path in output.iterdir()} == expected
    assert stat.S_IMODE(env_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(output.stat().st_mode) == 0o700
    assert all(stat.S_IMODE(path.stat().st_mode) == 0o600 for path in output.iterdir())


def test_redundant_resource_overrides_are_pruned(tmp_path: Path) -> None:
    """Verify that redundant resource overrides are pruned."""
    env_path = tmp_path / ".env"
    env_path.write_text(
        "APP_ENV=test\n"
        "ASSISTANT_GOOGLE_ANALYTICS_PROPERTY_IDS=duplicate\n"
        "ASSISTANT_GOOGLE_ADS_CUSTOMER_IDS=duplicate\n"
        "ASSISTANT_SOURCES_YAML_B64=keep\n"
    )

    module.prune(env_path)

    assert env_path.read_text() == "APP_ENV=test\nASSISTANT_SOURCES_YAML_B64=keep\n"
