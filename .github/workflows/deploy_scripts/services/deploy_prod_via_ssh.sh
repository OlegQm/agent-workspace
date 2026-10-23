#!/usr/bin/env bash
set -Eeuo pipefail

: "${DEPLOY_SSH_HOST:?DEPLOY_SSH_HOST is required}"
: "${DEPLOY_SSH_USER:?DEPLOY_SSH_USER is required}"
: "${DEPLOY_SSH_KEY_PATH:?DEPLOY_SSH_KEY_PATH is required}"
: "${DEPLOY_SSH_KNOWN_HOSTS_PATH:?DEPLOY_SSH_KNOWN_HOSTS_PATH is required}"
: "${REMOTE_APP_DIR:?REMOTE_APP_DIR is required}"
: "${DEPLOY_REPO_URL:?DEPLOY_REPO_URL is required}"
: "${DEPLOY_SHA:?DEPLOY_SHA is required}"
: "${GHCR_USERNAME:?GHCR_USERNAME is required}"
: "${DEPLOY_TOKEN_PATH:?DEPLOY_TOKEN_PATH is required}"
: "${DEPLOY_ENV_PATH:?DEPLOY_ENV_PATH is required}"

DEPLOY_SSH_PORT="${DEPLOY_SSH_PORT:-22}"
DEPLOY_GIT_REMOTE="${DEPLOY_GIT_REMOTE:-origin}"
REMOTE_NONCE="$(od -An -N8 -tx1 /dev/urandom | tr -d ' \n')"
REMOTE_TEMP_DIR="/tmp/open-agent-workspace-deploy-${GITHUB_RUN_ID:-manual}-${REMOTE_NONCE}"
REMOTE_TOKEN_PATH="${REMOTE_TEMP_DIR}/token"
REMOTE_ENV_PATH="${REMOTE_TEMP_DIR}/runtime.env"

SSH_OPTS=(
  -i "${DEPLOY_SSH_KEY_PATH}"
  -p "${DEPLOY_SSH_PORT}"
  -o BatchMode=yes
  -o IdentitiesOnly=yes
  -o StrictHostKeyChecking=yes
  -o "UserKnownHostsFile=${DEPLOY_SSH_KNOWN_HOSTS_PATH}"
)
SCP_OPTS=(
  -i "${DEPLOY_SSH_KEY_PATH}"
  -P "${DEPLOY_SSH_PORT}"
  -o BatchMode=yes
  -o IdentitiesOnly=yes
  -o StrictHostKeyChecking=yes
  -o "UserKnownHostsFile=${DEPLOY_SSH_KNOWN_HOSTS_PATH}"
)
REMOTE="${DEPLOY_SSH_USER}@${DEPLOY_SSH_HOST}"
printf -v REMOTE_PREPARE_COMMAND \
  'umask 077 && mkdir -- %q' "${REMOTE_TEMP_DIR}"
printf -v REMOTE_CLEANUP_COMMAND \
  'rm -rf -- %q' "${REMOTE_TEMP_DIR}"
printf -v REMOTE_CHMOD_COMMAND \
  'chmod 600 %q %q' "${REMOTE_TOKEN_PATH}" "${REMOTE_ENV_PATH}"
printf -v REMOTE_DEPLOY_COMMAND \
  'bash -s -- %q %q %q %q %q %q %q' \
  "${REMOTE_APP_DIR}" \
  "${DEPLOY_REPO_URL}" \
  "${DEPLOY_SHA}" \
  "${DEPLOY_GIT_REMOTE}" \
  "${GHCR_USERNAME}" \
  "${REMOTE_TOKEN_PATH}" \
  "${REMOTE_ENV_PATH}"

cleanup_remote() {
  # The command was constructed locally with Bash %q escaping.
  # shellcheck disable=SC2029
  ssh "${SSH_OPTS[@]}" "${REMOTE}" \
    "${REMOTE_CLEANUP_COMMAND}" >/dev/null 2>&1 || true
}
trap cleanup_remote EXIT

# The command was constructed locally with Bash %q escaping.
# shellcheck disable=SC2029
ssh "${SSH_OPTS[@]}" "${REMOTE}" "${REMOTE_PREPARE_COMMAND}"
scp "${SCP_OPTS[@]}" "${DEPLOY_TOKEN_PATH}" "${REMOTE}:${REMOTE_TOKEN_PATH}"
scp "${SCP_OPTS[@]}" "${DEPLOY_ENV_PATH}" "${REMOTE}:${REMOTE_ENV_PATH}"
# The command was constructed locally with Bash %q escaping.
# shellcheck disable=SC2029
ssh "${SSH_OPTS[@]}" "${REMOTE}" \
  "${REMOTE_CHMOD_COMMAND}"

# The command was constructed locally with Bash %q escaping.
# shellcheck disable=SC2029
ssh "${SSH_OPTS[@]}" "${REMOTE}" \
  "${REMOTE_DEPLOY_COMMAND}" \
  < .github/workflows/deploy_scripts/services/remote_deploy_prod.sh
