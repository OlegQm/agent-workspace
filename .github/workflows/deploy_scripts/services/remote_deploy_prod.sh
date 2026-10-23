#!/usr/bin/env bash
set -Eeuo pipefail

REMOTE_APP_DIR="${1:?remote application directory is required}"
DEPLOY_REPO_URL="${2:?repository URL is required}"
DEPLOY_SHA="${3:?deployment commit SHA is required}"
DEPLOY_GIT_REMOTE="${4:-origin}"
GHCR_USERNAME="${5:?GHCR username is required}"
DEPLOY_TOKEN_FILE="${6:?deployment token file is required}"
DEPLOY_ENV_FILE="${7:?deployment environment file is required}"

COMPOSE_PROJECT_NAME="open-agent-workspace-ai-workspace"
BASE_COMPOSE_FILE="infra/orchestration/docker-compose/docker-compose.yml"
PROD_COMPOSE_FILE="infra/orchestration/docker-compose/docker-compose.prod.yml"
PREVIOUS_SHA=""
ENV_BACKUP=""
DEPLOY_COMPLETE=false
GHCR_LOGGED_IN=false

log() { printf '[open-agent-workspace-deploy] %s\n' "$*"; }
die() { printf '[open-agent-workspace-deploy] ERROR: %s\n' "$*" >&2; exit 1; }

cleanup() {
  if [[ "${GHCR_LOGGED_IN}" == true ]]; then
    docker logout ghcr.io >/dev/null 2>&1 || true
  fi
  rm -f "${DEPLOY_TOKEN_FILE}" "${DEPLOY_ENV_FILE}"
  if [[ -n "${ENV_BACKUP}" && -f "${ENV_BACKUP}" ]]; then
    rm -f "${ENV_BACKUP}"
  fi
}

docker_cmd() {
  docker "$@"
}

compose_cmd() {
  local tool_gateway_dns
  tool_gateway_dns="$("${REMOTE_APP_DIR}/scripts/resolve_host_dns.sh")"
  TOOL_GATEWAY_DNS="${tool_gateway_dns}" docker_cmd compose \
    --project-name "${COMPOSE_PROJECT_NAME}" \
    --env-file "${REMOTE_APP_DIR}/.env" \
    -f "${REMOTE_APP_DIR}/${BASE_COMPOSE_FILE}" \
    -f "${REMOTE_APP_DIR}/${PROD_COMPOSE_FILE}" \
    "$@"
}

rollback() {
  local exit_code=$?
  trap - ERR
  if [[ "${DEPLOY_COMPLETE}" != true ]]; then
    log "Deployment failed; attempting to restore the previous revision"
    if [[ -n "${PREVIOUS_SHA}" && -d "${REMOTE_APP_DIR}/.git" ]]; then
      git -C "${REMOTE_APP_DIR}" checkout --detach --force "${PREVIOUS_SHA}" || true
    fi
    if [[ -n "${ENV_BACKUP}" && -f "${ENV_BACKUP}" ]]; then
      install -m 0600 "${ENV_BACKUP}" "${REMOTE_APP_DIR}/.env"
      if [[ -f "${REMOTE_APP_DIR}/${PROD_COMPOSE_FILE}" ]]; then
        compose_cmd up -d --no-build --remove-orphans || true
      fi
    fi
  fi
  cleanup
  exit "${exit_code}"
}

trap cleanup EXIT
trap rollback ERR

[[ "${DEPLOY_SHA}" =~ ^[0-9a-f]{40}$ ]] || die "DEPLOY_SHA must be a full commit SHA"
[[ -s "${DEPLOY_TOKEN_FILE}" ]] || die "Deployment token file is empty"
[[ -s "${DEPLOY_ENV_FILE}" ]] || die "Deployment environment file is empty"
command -v git >/dev/null 2>&1 || die "git is not installed"
command -v curl >/dev/null 2>&1 || die "curl is not installed"
command -v python3 >/dev/null 2>&1 || die "python3 is not installed"
command -v docker >/dev/null 2>&1 || die "Docker is not installed"
docker info >/dev/null 2>&1 || die "The deploy user cannot access the Docker daemon"
docker compose version >/dev/null 2>&1 || die "Docker Compose is unavailable"

DEPLOY_TOKEN="$(<"${DEPLOY_TOKEN_FILE}")"
[[ -n "${DEPLOY_TOKEN}" ]] || die "Deployment token is empty"
AUTH_HEADER="$(printf 'x-access-token:%s' "${DEPLOY_TOKEN}" | base64 | tr -d '\n')"

mkdir -p "${REMOTE_APP_DIR}"
REMOTE_APP_DIR="$(cd "${REMOTE_APP_DIR}" && pwd -P)"
if [[ "${REMOTE_APP_DIR}" == "/" || "${REMOTE_APP_DIR}" == "${HOME}" ]]; then
  die "REMOTE_APP_DIR must be a dedicated subdirectory"
fi

if [[ ! -d "${REMOTE_APP_DIR}/.git" ]]; then
  log "Initializing the deployment checkout"
  git init "${REMOTE_APP_DIR}" >/dev/null
fi

if git -C "${REMOTE_APP_DIR}" remote get-url "${DEPLOY_GIT_REMOTE}" >/dev/null 2>&1; then
  git -C "${REMOTE_APP_DIR}" remote set-url "${DEPLOY_GIT_REMOTE}" "${DEPLOY_REPO_URL}"
else
  git -C "${REMOTE_APP_DIR}" remote add "${DEPLOY_GIT_REMOTE}" "${DEPLOY_REPO_URL}"
fi

PREVIOUS_SHA="$(git -C "${REMOTE_APP_DIR}" rev-parse HEAD 2>/dev/null || true)"
log "Fetching commit ${DEPLOY_SHA:0:12}"
git -C "${REMOTE_APP_DIR}" \
  -c "http.extraheader=AUTHORIZATION: basic ${AUTH_HEADER}" \
  fetch --no-tags "${DEPLOY_GIT_REMOTE}" "${DEPLOY_SHA}"
git -C "${REMOTE_APP_DIR}" checkout --detach --force "${DEPLOY_SHA}"

log "Checking Docker Sandbox host requirements"
"${REMOTE_APP_DIR}/scripts/workspace.sh" host-check

mkdir -p \
  "${REMOTE_APP_DIR}/data/agents" \
  "${REMOTE_APP_DIR}/data/audit" \
  "${REMOTE_APP_DIR}/data/cache" \
  "${REMOTE_APP_DIR}/data/code" \
  "${REMOTE_APP_DIR}/data/exports" \
  "${REMOTE_APP_DIR}/data/runtime-secrets"
chmod 0700 "${REMOTE_APP_DIR}/data/agents" "${REMOTE_APP_DIR}/data/runtime-secrets"

if [[ -f "${REMOTE_APP_DIR}/.env" ]]; then
  ENV_BACKUP="$(mktemp)"
  install -m 0600 "${REMOTE_APP_DIR}/.env" "${ENV_BACKUP}"
fi

set -a
# The payload is generated with shell-safe quoting and never logged.
# shellcheck source=/dev/null
source "${DEPLOY_ENV_FILE}"
set +a

for required in \
  APP_SECRET_KEY POSTGRES_DB POSTGRES_USER POSTGRES_PASSWORD \
  BACKEND_IMAGE FRONTEND_IMAGE TOOL_GATEWAY_IMAGE CODE_SYNC_IMAGE; do
  [[ -n "${!required:-}" ]] || die "${required} is missing from the deployment payload"
done

{
  cat "${DEPLOY_ENV_FILE}"
  printf 'HOST_UID=%s\n' "$(id -u)"
  printf 'HOST_GID=%s\n' "$(id -g)"
} >"${REMOTE_APP_DIR}/.env.next"
chmod 0600 "${REMOTE_APP_DIR}/.env.next"
mv "${REMOTE_APP_DIR}/.env.next" "${REMOTE_APP_DIR}/.env"

log "Rendering scoped runtime credentials"
"${REMOTE_APP_DIR}/scripts/workspace.sh" runtime-prepare

log "Logging in to GHCR"
printf '%s' "${DEPLOY_TOKEN}" | docker_cmd login ghcr.io -u "${GHCR_USERNAME}" --password-stdin >/dev/null
GHCR_LOGGED_IN=true

log "Pulling immutable application images"
compose_cmd pull backend frontend tool-gateway-assistant code-sync
log "Starting the production stack"
compose_cmd up -d --no-build --remove-orphans

log "Applying database migrations"
compose_cmd exec -T --interactive=false backend open-agent-workspace-ai-admin migrate

log "Waiting for the HTTP health endpoint"
for _ in $(seq 1 60); do
  if [[ "$(compose_cmd ps --status running --services nginx)" == "nginx" ]] && \
    curl --fail --silent --show-error --max-time 3 \
    http://127.0.0.1/healthz >/dev/null 2>&1; then
    break
  fi
  sleep 2
done
[[ "$(compose_cmd ps --status running --services nginx)" == "nginx" ]] || \
  die "The edge nginx service is not running"
curl --fail --silent --show-error --max-time 5 http://127.0.0.1/healthz >/dev/null

compose_cmd ps
DEPLOY_COMPLETE=true
log "Deployment ${DEPLOY_SHA:0:12} completed"
