#!/bin/sh
case "$1" in
  *Username*) printf '%s\n' 'x-access-token' ;;
  *Password*) cat "${GITHUB_TOKEN_FILE:-/run/secrets/github-read-token}" ;;
  *) exit 1 ;;
esac
