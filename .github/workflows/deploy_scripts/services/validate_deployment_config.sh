#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
ENV_FILE="$(mktemp)"
trap 'rm -f "${ENV_FILE}"' EXIT

export APP_BASE_URL="http://192.0.2.10"
export APP_SECRET_KEY="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
export POSTGRES_DB="ai_workspace"
export POSTGRES_USER="ai_workspace"
export POSTGRES_PASSWORD="bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
export HERMES_API_KEY_ASSISTANT="cccccccccccccccccccccccccccccccc"
export TOOL_GATEWAY_TOKEN_ASSISTANT="eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"
export ASSISTANT_SOURCES_YAML_B64="e30="
export GOOGLE_SERVICE_ACCOUNT_JSON_B64="e30="
export CODE_SYNC_GITHUB_TOKEN_B64="ZHVtbXk="
export BACKEND_IMAGE="ghcr.io/example/project/backend:0123456789abcdef"
export FRONTEND_IMAGE="ghcr.io/example/project/frontend:0123456789abcdef"
export TOOL_GATEWAY_IMAGE="ghcr.io/example/project/tool-gateway:0123456789abcdef"
export CODE_SYNC_IMAGE="ghcr.io/example/project/code-sync:0123456789abcdef"

python3 "${ROOT}/.github/workflows/deploy_scripts/services/create_runtime_env.py" "${ENV_FILE}"
{
  printf 'HOST_UID=%s\n' "$(id -u)"
  printf 'HOST_GID=%s\n' "$(id -g)"
} >>"${ENV_FILE}"

TOOL_GATEWAY_DNS="$("${ROOT}/scripts/resolve_host_dns.sh")" docker compose \
  --env-file "${ENV_FILE}" \
  -f "${ROOT}/infra/orchestration/docker-compose/docker-compose.yml" \
  -f "${ROOT}/infra/orchestration/docker-compose/docker-compose.prod.yml" \
  config --quiet

printf 'Production deployment configuration is valid.\n'
