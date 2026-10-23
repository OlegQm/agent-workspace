#!/usr/bin/env bash
set -Eeuo pipefail

DEPLOY_USER="$(id -un)"
TASK_VERSION="3.52.0"

log() { printf '[open-agent-workspace-bootstrap] %s\n' "$*"; }
die() { printf '[open-agent-workspace-bootstrap] ERROR: %s\n' "$*" >&2; exit 1; }

[[ "$(uname -s)" == "Linux" ]] || die "A Linux host is required"
[[ "$(uname -m)" == "x86_64" ]] || die "The pinned sandbox image requires amd64"
command -v sudo >/dev/null 2>&1 || die "sudo is required"
sudo -n true >/dev/null 2>&1 || die "The deploy user needs passwordless sudo for host bootstrap"

log "Installing base packages"
sudo -n apt-get update
sudo -n apt-get install -y \
  ca-certificates curl git python3 python3-yaml qemu-kvm

if ! command -v docker >/dev/null 2>&1; then
  log "Installing Docker Engine"
  curl -fsSL https://get.docker.com | sudo -n sh
fi

if ! command -v sbx >/dev/null 2>&1; then
  log "Installing Docker Sandboxes"
  curl -fsSL https://get.docker.com | sudo -n REPO_ONLY=1 sh
  sudo -n apt-get update
  sudo -n apt-get install -y docker-sbx
fi

if ! command -v task >/dev/null 2>&1; then
  log "Installing Go Task ${TASK_VERSION}"
  task_archive="$(mktemp)"
  task_checksums="$(mktemp)"
  trap 'rm -f "${task_archive:-}" "${task_checksums:-}"' EXIT
  curl -fsSL \
    "https://github.com/go-task/task/releases/download/v${TASK_VERSION}/task_linux_amd64.tar.gz" \
    -o "${task_archive}"
  curl -fsSL \
    "https://github.com/go-task/task/releases/download/v${TASK_VERSION}/task_checksums.txt" \
    -o "${task_checksums}"
  expected="$(awk '$2 == "task_linux_amd64.tar.gz" {print $1}' "${task_checksums}")"
  actual="$(sha256sum "${task_archive}" | awk '{print $1}')"
  [[ -n "${expected}" && "${actual}" == "${expected}" ]] || die "Go Task checksum mismatch"
  sudo -n tar -xzf "${task_archive}" -C /usr/local/bin task
  sudo -n chmod 0755 /usr/local/bin/task
fi

sudo -n usermod -aG docker,kvm "${DEPLOY_USER}"
sudo -n systemctl enable --now docker

[[ -e /dev/kvm ]] || die "/dev/kvm is unavailable; enable virtualization in the server firmware"
docker compose version >/dev/null 2>&1 || die "Docker Compose was not installed"
sbx version >/dev/null 2>&1 || die "Docker Sandboxes was not installed"
task --version >/dev/null 2>&1 || die "Go Task was not installed"

log "Host prerequisites are installed"
log "Start a new SSH session before the first deployment so docker/kvm group membership applies"
