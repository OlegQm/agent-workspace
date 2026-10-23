#!/bin/sh
set -eu

: "${WORKDIR:?WORKDIR is required}"
export HERMES_HOME="${WORKDIR}/hermes-state"
# Repository access is provided only by the read-only Open Agent Workspace MCP mirrors.
unset GH_TOKEN GITHUB_TOKEN GITLAB_TOKEN BITBUCKET_TOKEN
mkdir -p "${HERMES_HOME}" "${WORKDIR}/workspace/outputs"
cd "${WORKDIR}/workspace"

exec hermes gateway run --external-supervisor --accept-hooks
