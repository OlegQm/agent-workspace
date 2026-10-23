#!/usr/bin/env bash
set -Eeuo pipefail

: "${DEPLOY_SSH_HOST:?DEPLOY_SSH_HOST is required}"
: "${DEPLOY_SSH_USER:?DEPLOY_SSH_USER is required}"
: "${DEPLOY_SSH_KEY_PATH:?DEPLOY_SSH_KEY_PATH is required}"
: "${DEPLOY_SSH_KNOWN_HOSTS_PATH:?DEPLOY_SSH_KNOWN_HOSTS_PATH is required}"

DEPLOY_SSH_PORT="${DEPLOY_SSH_PORT:-22}"
SSH_OPTS=(
  -i "${DEPLOY_SSH_KEY_PATH}"
  -p "${DEPLOY_SSH_PORT}"
  -o BatchMode=yes
  -o IdentitiesOnly=yes
  -o StrictHostKeyChecking=yes
  -o "UserKnownHostsFile=${DEPLOY_SSH_KNOWN_HOSTS_PATH}"
)

ssh "${SSH_OPTS[@]}" "${DEPLOY_SSH_USER}@${DEPLOY_SSH_HOST}" \
  "bash -s" < .github/workflows/deploy_scripts/infra/remote_bootstrap_host.sh
