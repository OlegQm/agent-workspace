#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE="${HERMES_VERIFY_IMAGE:-open-agent-workspace/hermes-agent:0.20.1-native-ci}"
CONTAINER="open-agent-workspace-hermes-native-ci-${RANDOM}"
STATE_DIR="$(mktemp -d)"
API_KEY="native-hermes-ci-key-123456"

cleanup() {
  if docker container inspect "${CONTAINER}" >/dev/null 2>&1; then
    docker rm -f "${CONTAINER}" >/dev/null 2>&1 || true
  fi
  if [[ -d "${STATE_DIR}" ]] && docker image inspect "${IMAGE}" >/dev/null 2>&1; then
    docker run --rm --user root \
      --entrypoint sh \
      -v "${STATE_DIR}:/state" \
      "${IMAGE}" \
      -c 'find /state -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +' \
      >/dev/null 2>&1 || true
  fi
  rm -rf "${STATE_DIR}" >/dev/null 2>&1 || true
}

print_container_diagnostics() {
  echo "Hermes verification container diagnostics:" >&2
  if ! docker container inspect "${CONTAINER}" >/dev/null 2>&1; then
    echo "Container ${CONTAINER} no longer exists; no logs are available." >&2
    return
  fi

  docker container inspect "${CONTAINER}" \
    --format 'status={{.State.Status}} exit_code={{.State.ExitCode}} error={{.State.Error}}' \
    >&2 || true
  docker logs "${CONTAINER}" >&2 || true
}

finish() {
  local status=$?
  trap - EXIT
  if ((status != 0)); then
    print_container_diagnostics
  fi
  cleanup
  exit "${status}"
}
trap finish EXIT

docker build --pull -t "${IMAGE}" "${ROOT}/infra/sandbox"

docker run --rm --entrypoint sh "${IMAGE}" -lc '
  hermes --version
  if command -v codex >/dev/null; then
    echo "Codex CLI must not be present in the native Hermes image" >&2
    exit 1
  fi
'

docker run --rm -i --entrypoint /opt/hermes/.venv/bin/python \
  --user "$(id -u):$(id -g)" \
  -v "${ROOT}/infra/sandbox/hermes-config.template.yaml:/tmp/config.yaml:ro" \
  "${IMAGE}" - <<'PY'
import yaml

from hermes_cli.tools_config import _get_platform_tools

config = yaml.safe_load(open("/tmp/config.yaml", encoding="utf-8"))
actual = _get_platform_tools(config, "api_server")
expected = {"terminal", "file", "todo", "vision", "web", "browser", "open-agent-workspace"}
if actual != expected:
    raise SystemExit(f"Unexpected Hermes toolsets: {sorted(actual)}")
PY

docker run --rm -i --entrypoint /opt/hermes/.venv/bin/python \
  --user "$(id -u):$(id -g)" \
  -v "${ROOT}/infra/sandbox/hermes-config.template.yaml:/tmp/config.yaml:ro" \
  -v "${STATE_DIR}:/state" \
  "${IMAGE}" - <<'PY'
from pathlib import Path

import yaml

config = yaml.safe_load(Path("/tmp/config.yaml").read_text(encoding="utf-8"))
config["mcp_servers"] = {}
config["platform_toolsets"]["api_server"].remove("open-agent-workspace")
Path("/state/config.yaml").write_text(yaml.safe_dump(config), encoding="utf-8")
PY
# The GitHub runner uses a different UID than the image's `agent` user. The
# directory contains only generated test configuration and is deleted on exit.
chmod 0777 "${STATE_DIR}"
chmod 0644 "${STATE_DIR}/config.yaml"

docker run -d --name "${CONTAINER}" \
  -e HERMES_HOME=/home/agent/.hermes \
  -e API_SERVER_ENABLED=true \
  -e API_SERVER_HOST=127.0.0.1 \
  -e API_SERVER_PORT=8642 \
  -e API_SERVER_KEY="${API_KEY}" \
  -v "${STATE_DIR}:/home/agent/.hermes" \
  "${IMAGE}" \
  hermes gateway run --external-supervisor --accept-hooks >/dev/null

ready=false
for _ in $(seq 1 60); do
  if docker exec "${CONTAINER}" curl --fail --silent \
    -H "Authorization: Bearer ${API_KEY}" \
    http://127.0.0.1:8642/v1/capabilities >/dev/null 2>&1; then
    ready=true
    break
  fi
  if [[ "$(docker container inspect "${CONTAINER}" --format '{{.State.Running}}' 2>/dev/null || true)" != true ]]; then
    break
  fi
  sleep 1
done
if [[ "${ready}" != true ]]; then
  exit 1
fi

docker exec "${CONTAINER}" curl --fail --silent \
  -H "Authorization: Bearer ${API_KEY}" \
  http://127.0.0.1:8642/v1/capabilities | python3 -c '
import json
import sys

payload = json.load(sys.stdin)
assert payload["features"]["session_resources"] is True
assert "session_messages" in payload["endpoints"]
'
docker exec "${CONTAINER}" curl --fail --silent \
  -H "Authorization: Bearer ${API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"id":"native_ci_session","source":"api_server"}' \
  http://127.0.0.1:8642/api/sessions >/dev/null
docker exec "${CONTAINER}" curl --fail --silent \
  -H "Authorization: Bearer ${API_KEY}" \
  http://127.0.0.1:8642/api/sessions/native_ci_session/messages | python3 -c '
import json
import sys

assert json.load(sys.stdin)["data"] == []
'
docker exec "${CONTAINER}" curl --fail --silent -X DELETE \
  -H "Authorization: Bearer ${API_KEY}" \
  http://127.0.0.1:8642/api/sessions/native_ci_session >/dev/null

echo "Native Hermes runtime verification passed."
