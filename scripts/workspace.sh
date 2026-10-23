#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="${ROOT}/infra/orchestration/docker-compose/docker-compose.yml"
SBX_IMAGE="open-agent-workspace/hermes-agent:0.20.1-native-sbx1"
MIN_SBX_VERSION="0.38.0"
GITHUB_DENY_RESOURCES="github.com,api.github.com,uploads.github.com,raw.githubusercontent.com,gist.githubusercontent.com,objects.githubusercontent.com,codeload.github.com"

log() { printf '[open-agent-workspace-ai] %s\n' "$*"; }
die() { printf '[open-agent-workspace-ai] ERROR: %s\n' "$*" >&2; exit 1; }
need() { command -v "$1" >/dev/null 2>&1 || die "$1 is required"; }

python_with_yaml() {
  if python3 -c 'import yaml' >/dev/null 2>&1; then
    python3 "$@"
    return
  fi
  need uv
  uv run --project "${ROOT}/service/backend" python "$@"
}

manifest_path() {
  local agent="${1:?agent is required}"
  local path="${ROOT}/config/agents/${agent}.yaml"
  [[ -f "${path}" ]] || die "Unknown agent: ${agent}"
  printf '%s' "${path}"
}

manifest_get() {
  local agent="$1" key="$2"
  python_with_yaml - "$(manifest_path "${agent}")" "${key}" <<'PY'
import sys, yaml
value = yaml.safe_load(open(sys.argv[1]))
for part in sys.argv[2].split('.'):
    value = value[part]
print(value)
PY
}

llm_field() {
  local agent="${1:?agent is required}" field="${2:?field is required}"
  uv run --project "${ROOT}/service/backend" --env-file "${ROOT}/config/llm.env" \
    python "${ROOT}/scripts/render_agent_hermes_config.py" \
    --manifest "$(manifest_path "${agent}")" --field "${field}"
}

env_get() {
  local key="$1"
  python3 - "${ROOT}/.env" "${key}" <<'PY'
import sys
path, wanted = sys.argv[1:]
for raw in open(path):
    line = raw.strip()
    if not line or line.startswith('#') or '=' not in line:
        continue
    key, value = line.split('=', 1)
    if key == wanted:
        print(value.strip().strip('"').strip("'"))
        break
PY
}

version_ge() {
  printf '%s\n%s\n' "$2" "$1" | sort -V -C
}

sbx_client_version() {
  local output
  output="$(sbx version 2>&1 || true)"
  sed -nE \
    -e 's/^[[:space:]]*Client Version:[[:space:]]+v?([0-9]+([.][0-9]+){1,2}).*/\1/p' \
    -e 's/^[[:space:]]*sbx version:[[:space:]]+v?([0-9]+([.][0-9]+){1,2}).*/\1/p' \
    <<<"${output}" | head -n 1
}

check_sbx_version() {
  need sbx
  local version
  version="$(sbx_client_version)"
  [[ -n "${version}" ]] || die "Could not determine sbx version"
  version_ge "${version}" "${MIN_SBX_VERSION}" || die "sbx >= ${MIN_SBX_VERSION} is required (installed: ${version})"
}

host_check() {
  local failed=0
  [[ "$(uname -s)" == Linux ]] || { log "FAIL Linux is required"; failed=1; }
  [[ -r /dev/kvm && -w /dev/kvm ]] || { log "FAIL /dev/kvm is unavailable to this user"; failed=1; }
  if ! command -v docker >/dev/null || ! docker info >/dev/null 2>&1; then
    log "FAIL Docker is unavailable"
    failed=1
  fi
  if command -v sbx >/dev/null; then
    local version
    version="$(sbx_client_version)"
    if [[ -n "${version}" ]] && version_ge "${version}" "${MIN_SBX_VERSION}"; then
      log "OK sbx ${version}"
    else
      log "FAIL sbx >= ${MIN_SBX_VERSION} is required (installed: ${version:-unknown})"
      failed=1
    fi
  else
    log "FAIL sbx is not installed"
    failed=1
  fi
  [[ "$(uname -m)" == x86_64 ]] || log "WARN the sandbox image is currently verified only on amd64"
  (( failed == 0 )) || return 1
  log "Host supports Docker Sandboxes"
}

host_bootstrap() {
  [[ "$(uname -s)" == Linux ]] || die "Ubuntu Linux is required"
  if ! command -v docker >/dev/null; then
    curl -fsSL https://get.docker.com | sudo sh
    sudo usermod -aG docker "${USER}"
  fi
  local sbx_version=""
  if command -v sbx >/dev/null; then
    sbx_version="$(sbx_client_version)"
  fi
  if [[ -z "${sbx_version}" ]] || ! version_ge "${sbx_version}" "${MIN_SBX_VERSION}"; then
    curl -fsSL https://get.docker.com | sudo REPO_ONLY=1 sh
    sudo apt-get update
    sudo apt-get install -y docker-sbx
  fi
  sudo usermod -aG kvm,docker "${USER}"
  log "Bootstrap complete. Re-login once if group membership changed."
}

create_env() {
  local created=false
  umask 077
  if [[ ! -f "${ROOT}/.env" ]]; then
    cp "${ROOT}/.env.example" "${ROOT}/.env"
    created=true
  fi
  ROOT="${ROOT}" python3 <<'PY'
from pathlib import Path
import os, secrets
path = Path(os.environ['ROOT']) / '.env'
text = path.read_text()
postgres = secrets.token_urlsafe(32)
replacements = {
    'APP_SECRET_KEY=replace-with-openssl-rand-hex-32': f'APP_SECRET_KEY={secrets.token_hex(32)}',
    'POSTGRES_PASSWORD=replace-me': f'POSTGRES_PASSWORD={postgres}',
    'DATABASE_URL=postgresql+asyncpg://ai_workspace:replace-me@127.0.0.1:55432/ai_workspace': f'DATABASE_URL=postgresql+asyncpg://ai_workspace:{postgres}@127.0.0.1:55432/ai_workspace',
    'HERMES_API_KEY_ASSISTANT=replace-me': f'HERMES_API_KEY_ASSISTANT={secrets.token_hex(32)}',
    'TOOL_GATEWAY_TOKEN_ASSISTANT=replace-me': f'TOOL_GATEWAY_TOKEN_ASSISTANT={secrets.token_hex(32)}',
}

text = text.replace('HOST_UID=1000', f'HOST_UID={os.getuid()}')
text = text.replace('HOST_GID=1000', f'HOST_GID={os.getgid()}')
for old, new in replacements.items():
    text = text.replace(old, new)
path.write_text(text)
PY
  if [[ "${created}" == true ]]; then
    log "Created .env with local application secrets; configure PROD read-only credentials before tool smoke tests"
  fi
}

build_sandbox_image() {
  if ! docker image inspect "${SBX_IMAGE}" >/dev/null 2>&1; then
    docker build --pull -t "${SBX_IMAGE}" "${ROOT}/infra/sandbox"
  fi
  if sbx template ls 2>/dev/null | grep -qE 'open-agent-workspace/hermes-agent[[:space:]]+0.20.1-native-sbx1'; then
    return
  fi
  local image_tar="${ROOT}/data/cache/open-agent-workspace-hermes-agent.tar"
  mkdir -p "$(dirname "${image_tar}")"
  docker save -o "${image_tar}" "${SBX_IMAGE}"
  sbx template load "${image_tar}"
}

write_agent_state() {
  local agent="$1"
  local data="${ROOT}/data/agents/${agent}"
  local key_env key display_name gateway_port credential_env credential_key
  key_env="$(manifest_get "${agent}" hermes_api_key_env)"
  key="$(env_get "${key_env}")"
  display_name="$(manifest_get "${agent}" display_name)"
  gateway_port="$(manifest_get "${agent}" tool_gateway_port)"
  [[ ${#key} -ge 16 ]] || die "${key_env} must contain at least 16 characters"
  validate_hermes_config_template
  if [[ "$(llm_field "${agent}" auth_method)" == api_key ]]; then
    credential_env="$(llm_field "${agent}" credential_env)"
    credential_key="$(env_get "${credential_env}")"
    [[ -n "${credential_key}" ]] || die "${credential_env} is required for ${agent}"
  fi
  mkdir -p "${data}/workspace/outputs" "${data}/hermes-state" "${ROOT}/data/generated-kits/${agent}"
  chmod 0700 "${data}/hermes-state"
  (umask 077; cat >"${data}/hermes-state/.env" <<EOF
API_SERVER_ENABLED=true
API_SERVER_HOST=0.0.0.0
API_SERVER_PORT=8642
API_SERVER_KEY=${key}
EOF
  )
  if [[ -n "${credential_env:-}" ]]; then
    printf '%s=%s\n' "${credential_env}" "${credential_key}" >>"${data}/hermes-state/.env"
  fi
  chmod 0600 "${data}/hermes-state/.env"
  uv run --project "${ROOT}/service/backend" --env-file "${ROOT}/config/llm.env" \
    python "${ROOT}/scripts/render_agent_hermes_config.py" \
    --manifest "$(manifest_path "${agent}")" \
    --template "${ROOT}/infra/sandbox/hermes-config.template.yaml" \
    --workspace "${data}/workspace" \
    --tool-gateway-port "${gateway_port}" \
    --output "${data}/hermes-state/config.yaml"
  install_agent_prompt "${agent}" "${data}/hermes-state/SOUL.md"
  AGENT_ID="${agent}" DISPLAY_NAME="${display_name}" TOOL_GATEWAY_PORT="${gateway_port}" ROOT="${ROOT}" python3 <<'PY'
from pathlib import Path
import os
root = Path(os.environ['ROOT'])
text = (root / 'infra/sandbox/kit/spec.template.yaml').read_text()
for key in ('AGENT_ID', 'DISPLAY_NAME', 'TOOL_GATEWAY_PORT'):
    text = text.replace(f'__{key}__', os.environ[key])
target = root / 'data/generated-kits' / os.environ['AGENT_ID'] / 'spec.yaml'
target.write_text(text)
PY
}

validate_hermes_config_template() {
  python_with_yaml - "${ROOT}/infra/sandbox/hermes-config.template.yaml" <<'PY'
import sys
import yaml

config = yaml.safe_load(open(sys.argv[1], encoding="utf-8"))
assert config["platform_toolsets"]["api_server"] == [
    "terminal", "file", "todo", "vision", "web", "browser", "open-agent-workspace"
]
assert set(config["agent"]["disabled_toolsets"]) == {
    "memory",
    "session_search",
    "skills",
    "delegation",
    "cronjob",
    "bfl",
    "context_engine",
    "kanban",
}
PY
  local manifest
  for manifest in "${ROOT}"/config/agents/*.yaml; do
    [[ -f "${manifest}" ]] || continue
    uv run --project "${ROOT}/service/backend" --env-file "${ROOT}/config/llm.env" \
      python "${ROOT}/scripts/render_agent_hermes_config.py" \
      --manifest "${manifest}" \
      --template "${ROOT}/infra/sandbox/hermes-config.template.yaml" --check
  done
}

install_agent_prompt() {
  local agent="${1:?agent is required}" destination="${2:?destination is required}"
  local source="${ROOT}/config/agents/prompts/${agent}/SOUL.md"
  [[ -f "${source}" ]] || die "Hermes prompt not found: ${source}"
  install -m 0600 "${source}" "${destination}"
}

agent_create() {
  local agent="${1:?agent is required}"
  check_sbx_version
  create_env
  write_agent_state "${agent}"
  build_sandbox_image
  local sandbox host_port data kit token_env token
  sandbox="$(manifest_get "${agent}" sandbox_name)"
  host_port="$(manifest_get "${agent}" host_port)"
  data="${ROOT}/data/agents/${agent}"
  kit="${ROOT}/data/generated-kits/${agent}"
  token_env="$(manifest_get "${agent}" tool_gateway_token_env)"
  token="$(env_get "${token_env}")"
  if sbx ls --json 2>/dev/null | grep -q "\"${sandbox}\""; then
    die "Sandbox ${sandbox} already exists"
  fi
  sbx kit validate "${kit}"
  sbx secret rm "open-agent-workspace-gateway-${agent}" -f >/dev/null 2>&1 || true
  printf '%s' "${token}" | sbx secret set "open-agent-workspace-gateway-${agent}"
  sbx create shell "${data}" --name "${sandbox}" --memory 8g --cpus 4 \
    --template "${SBX_IMAGE}" --kit "${kit}" --no-share-skills \
    --deny-network "${GITHUB_DENY_RESOURCES}" \
    --publish "127.0.0.1:${host_port}:8642"
  printf '%s' "${token}" | sbx secret set "open-agent-workspace-gateway-${agent}" --sandbox "${sandbox}"
  sbx secret rm "open-agent-workspace-gateway-${agent}" -f >/dev/null
  agent_start "${agent}"
  log "Created ${sandbox}; run 'task agent:auth AGENT=${agent}' to authorize Hermes"
}

agent_start() {
  local agent="${1:?agent is required}" sandbox data pid_file pid remote_command
  sandbox="$(manifest_get "${agent}" sandbox_name)"
  data="${ROOT}/data/agents/${agent}"
  pid_file="${data}/sbx-keepalive.pid"
  if [[ -f "${pid_file}" ]]; then
    pid="$(cat "${pid_file}")"
    if kill -0 "${pid}" 2>/dev/null; then
      log "${sandbox} is already supervised by PID ${pid}"
      return
    fi
    rm -f "${pid_file}"
  fi
  remote_command='exec env WORKDIR="${WORKSPACE_DIR:?WORKSPACE_DIR is required}" /usr/local/bin/start-open-agent-workspace-hermes'
  # The positional parameters are intentionally expanded by the child shell.
  # shellcheck disable=SC2016
  nohup setsid bash -c '
    trap "exit 0" TERM INT
    while true; do
      "$1" exec "$2" -- sh -lc "$3" || true
      sleep 1
    done
  ' _ "$(command -v sbx)" "${sandbox}" "${remote_command}" >"${data}/sbx-keepalive.log" 2>&1 &
  pid=$!
  printf '%s\n' "${pid}" >"${pid_file}"
  sleep 1
  if ! kill -0 "${pid}" 2>/dev/null; then
    rm -f "${pid_file}"
    die "Failed to start ${sandbox}; see ${data}/sbx-keepalive.log"
  fi
  log "Started ${sandbox} with keepalive PID ${pid}"
}

agent_stop() {
  local agent="${1:?agent is required}" sandbox data pid_file pid
  sandbox="$(manifest_get "${agent}" sandbox_name)"
  data="${ROOT}/data/agents/${agent}"
  pid_file="${data}/sbx-keepalive.pid"
  if [[ -f "${pid_file}" ]]; then
    pid="$(cat "${pid_file}")"
    kill -- "-${pid}" 2>/dev/null || kill "${pid}" 2>/dev/null || true
    rm -f "${pid_file}"
  fi
  sbx stop "${sandbox}"
}
agent_status() {
  if [[ -n "${1:-}" ]]; then sbx inspect "$(manifest_get "$1" sandbox_name)"; else sbx ls; fi
}
agent_auth() {
  local agent="${1:?agent is required}" sandbox data provider
  if [[ "$(llm_field "${agent}" auth_method)" == api_key ]]; then
    log "${agent} uses API-key authentication; configure its credential and run runtime:prepare"
    return
  fi
  provider="$(llm_field "${agent}" provider)"
  sandbox="$(manifest_get "${agent}" sandbox_name)"
  data="${ROOT}/data/agents/${agent}"
  log "Hermes login for ${agent}: complete the device-code authorization"
  sbx exec -it "${sandbox}" -- sh -lc \
    "HERMES_HOME='${data}/hermes-state' hermes auth add ${provider} --no-browser"
}

compose() {
  local tool_gateway_dns
  tool_gateway_dns="$("${ROOT}/scripts/resolve_host_dns.sh")"
  TOOL_GATEWAY_DNS="${tool_gateway_dns}" docker compose \
    --env-file "${ROOT}/.env" -f "${COMPOSE_FILE}" "$@"
}

render_runtime_secrets() {
  python_with_yaml "${ROOT}/scripts/render_runtime_secrets.py" prune \
    --env "${ROOT}/.env"
  python_with_yaml "${ROOT}/scripts/render_runtime_secrets.py" render \
    --env "${ROOT}/.env" \
    --output-dir "${ROOT}/data/runtime-secrets"
}

sync_agent_runtime_config() {
  local manifest agent state_dir
  for manifest in "${ROOT}"/config/agents/*.yaml; do
    [[ -f "${manifest}" ]] || continue
    agent="$(basename "${manifest}" .yaml)"
    state_dir="${ROOT}/data/agents/${agent}/hermes-state"
    if [[ -d "${state_dir}" ]]; then
      write_agent_state "${agent}"
    fi
  done
}

runtime_prepare() {
  [[ -f "${ROOT}/.env" ]] || die ".env must exist before runtime preparation"
  mkdir -p "${ROOT}/data/agents" "${ROOT}/data/exports" "${ROOT}/data/code" \
    "${ROOT}/data/audit" "${ROOT}/data/runtime-secrets"
  render_runtime_secrets
  sync_agent_runtime_config
  log "Runtime directories, scoped credentials, and agent configuration are ready"
}

up() {
  create_env
  render_runtime_secrets
  sync_agent_runtime_config
  compose up -d --build
  python3 "${ROOT}/scripts/wait_for_backend.py"
}

setup() {
  need docker
  docker info >/dev/null 2>&1 || die "Docker daemon is unavailable"
  if ! host_check >/dev/null 2>&1; then
    log "WARN web stack will start, but agent microVMs require the host:check issues to be fixed"
  fi
  create_env
  mkdir -p "${ROOT}/data/agents" "${ROOT}/data/exports" "${ROOT}/data/code" \
    "${ROOT}/data/audit" "${ROOT}/data/runtime-secrets"
  render_runtime_secrets
  sync_agent_runtime_config
  compose up -d --build
  compose exec -T backend open-agent-workspace-ai-admin migrate
  python3 "${ROOT}/scripts/wait_for_backend.py"
  log "Web stack is running at http://localhost. Register accounts explicitly with task user:create AGENT=assistant or task admin:create USERNAME=admin"
}

user_create() {
  local agent="${1:?agent is required}" username locale
  username="$(manifest_get "${agent}" username)"
  locale="$(manifest_get "${agent}" locale)"
  compose exec backend open-agent-workspace-ai-admin create-user "${username}" "${agent}" --locale "${locale}"
}

admin_create() {
  local username="${1:?administrator username is required}"
  compose exec backend open-agent-workspace-ai-admin create-admin "${username}" --locale "en"
}

agent_export() {
  local agent="${1:?agent is required}" stamp stage archive data pid_file pid restart=false
  stamp="$(date -u +%Y%m%dT%H%M%SZ)"
  stage="$(mktemp -d)"
  archive="${ROOT}/data/exports/${agent}-${stamp}.tar.gz"
  data="${ROOT}/data/agents/${agent}"
  pid_file="${data}/sbx-keepalive.pid"
  if [[ -f "${pid_file}" ]]; then
    pid="$(cat "${pid_file}")"
    if kill -0 "${pid}" 2>/dev/null; then
      restart=true
      agent_stop "${agent}"
    fi
  fi
  trap 'rm -rf "${stage}"; if [[ "${restart}" == true ]]; then agent_start "${agent}"; fi' RETURN
  mkdir -p "${stage}/config" "${stage}/data/hermes-state"
  cp "$(manifest_path "${agent}")" "${stage}/config/agent.yaml"
  cp -a "${data}/workspace" "${stage}/data/workspace"
  if [[ -d "${data}/hermes-state" ]]; then
    rsync -a \
      --exclude='.env' --exclude='auth.json' --exclude='*credential*' \
      --exclude='openai_codex*' --exclude='.codex' \
      "${data}/hermes-state/" "${stage}/data/hermes-state/"
  fi
  compose exec -T backend open-agent-workspace-ai-admin export-history "${agent}" >"${stage}/history.json"
  tar -C "${stage}" -czf "${archive}" .
  log "Exported ${archive}. OAuth state, source credentials, passwords, and Hermes API keys are excluded."
}

agent_import() {
  local agent="${1:?agent is required}" archive="${2:?archive is required}" stage data username
  [[ -f "${archive}" ]] || die "Archive not found: ${archive}"
  stage="$(mktemp -d)"
  trap 'rm -rf "${stage}"' RETURN
  tar -C "${stage}" -xzf "${archive}"
  python_with_yaml - "${stage}/config/agent.yaml" "${agent}" <<'PY'
import sys, yaml
manifest = yaml.safe_load(open(sys.argv[1]))
if manifest.get('id') != sys.argv[2]:
    raise SystemExit('Archive agent ID does not match')
PY
  data="${ROOT}/data/agents/${agent}"
  [[ ! -e "${data}" ]] || die "Destination ${data} already exists"
  mkdir -p "${data}"
  cp -a "${stage}/data/workspace" "${data}/workspace"
  cp -a "${stage}/data/hermes-state" "${data}/hermes-state"
  write_agent_state "${agent}"
  user_create "${agent}"
  username="$(manifest_get "${agent}" username)"
  compose exec -T backend open-agent-workspace-ai-admin import-history "${agent}" "${username}" <"${stage}/history.json"
  log "Imported ${agent}. Reconfigure source credentials, then create and authorize its sandbox."
}

docs_check() {
  node --test "${ROOT}/scripts/tests/check_docs.test.mjs"
  node "${ROOT}/scripts/check_docs.mjs" "${ROOT}"
}

lint() {
  docs_check
  validate_hermes_config_template
  python3 "${ROOT}/scripts/check_docstrings.py" "${ROOT}"
  uv run --project "${ROOT}/service/tool-gateway" --extra dev ruff check \
    "${ROOT}/scripts/render_runtime_secrets.py" \
    "${ROOT}/.github/workflows/deploy_scripts/services/create_runtime_env.py"
  uv run --project "${ROOT}/service/backend" --extra dev ruff check "${ROOT}/service/backend/src" "${ROOT}/service/backend/tests"
  uv run --project "${ROOT}/service/backend" --extra dev lint-imports --config "${ROOT}/service/backend/.importlinter"
  uv run --project "${ROOT}/service/tool-gateway" --extra dev ruff check "${ROOT}/service/tool-gateway/src" "${ROOT}/service/tool-gateway/tests"
  uv run --project "${ROOT}/service/tool-gateway" --extra dev lint-imports --config "${ROOT}/service/tool-gateway/.importlinter"
  uv run --project "${ROOT}/service/code-sync" --extra dev ruff check "${ROOT}/service/code-sync/src" "${ROOT}/service/code-sync/tests"
  npm --prefix "${ROOT}/service/frontend" run typecheck
  bash -n \
    "$0" \
    "${ROOT}/scripts/resolve_host_dns.sh" \
    "${ROOT}/scripts/verify_hermes_runtime.sh" \
    "${ROOT}/.github/workflows/deploy_scripts/services/deploy_prod_via_ssh.sh" \
    "${ROOT}/.github/workflows/deploy_scripts/infra/bootstrap_host_via_ssh.sh" \
    "${ROOT}/.github/workflows/deploy_scripts/services/remote_deploy_prod.sh" \
    "${ROOT}/.github/workflows/deploy_scripts/infra/remote_bootstrap_host.sh" \
    "${ROOT}/.github/workflows/deploy_scripts/services/validate_deployment_config.sh"
}

deployment_validate() {
  need docker
  "${ROOT}/.github/workflows/deploy_scripts/services/validate_deployment_config.sh"
}

test_all() {
  node --test "${ROOT}/scripts/tests/wait_for_backend.test.mjs"
  uv run --project "${ROOT}/service/backend" --extra dev pytest \
    "${ROOT}/service/backend/tests" \
    --cov=bootstrap \
    --cov=entrypoints \
    --cov=features \
    --cov=infrastructure \
    --cov-branch \
    --cov-report=term-missing:skip-covered \
    --cov-fail-under=100
  uv run --project "${ROOT}/service/tool-gateway" --extra dev pytest \
    "${ROOT}/service/tool-gateway/tests" \
    --cov=tool_gateway \
    --cov-branch \
    --cov-report=term-missing:skip-covered \
    --cov-fail-under=100
  uv run --project "${ROOT}/service/code-sync" --extra dev pytest "${ROOT}/service/code-sync/tests"
  npm --prefix "${ROOT}/service/frontend" run test
  deployment_validate
}

code_sync() {
  render_runtime_secrets
  compose run --rm code-sync once
}

code_status() {
  render_runtime_secrets
  compose run --rm --no-deps code-sync status
}

help_text() {
  cat <<'EOF'
Open Agent Workspace

  task host:check
  task host:bootstrap
  task setup
  task runtime:prepare
  task runtime:verify
  task agent:create AGENT=assistant
  task agent:auth AGENT=assistant
  task user:create AGENT=assistant
  task admin:create USERNAME=admin
  task agent:export AGENT=assistant
  task agent:import AGENT=assistant ARCHIVE=/path/export.tar.gz
  task code:sync
  task code:status
  task deploy:validate
  task docs:check
EOF
}

command="${1:-help}"
shift || true
case "${command}" in
  help) help_text ;;
  host-check|host:check) host_check ;;
  host-bootstrap|host:bootstrap) host_bootstrap ;;
  setup) setup ;;
  up) up ;;
  runtime-prepare|runtime:prepare) runtime_prepare ;;
  agent-create|agent:create) agent_create "$@" ;;
  agent-start|agent:start) agent_start "$@" ;;
  agent-stop|agent:stop) agent_stop "$@" ;;
  agent-status|agent:status) agent_status "$@" ;;
  agent-auth|agent:auth) agent_auth "$@" ;;
  agent-export|agent:export) agent_export "$@" ;;
  agent-import|agent:import) agent_import "$@" ;;
  code-sync|code:sync) code_sync ;;
  code-status|code:status) code_status ;;
  deploy-validate|deploy:validate) deployment_validate ;;
  docs-check|docs:check) docs_check ;;
  user-create|user:create) user_create "$@" ;;
  admin-create|admin:create) admin_create "$@" ;;
  lint) lint ;;
  test) test_all ;;
  *) die "Unknown command: ${command}" ;;
esac
