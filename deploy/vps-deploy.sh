#!/usr/bin/env bash
# VPS helper: runs Compose with the production files from the repo root.
# Usage (on Linux): bash deploy/vps-deploy.sh up -d --build
#
# Optional services via Compose profiles (Compose honors the COMPOSE_PROFILES env var), e.g. Hardhat:
#   COMPOSE_PROFILES=blockchain bash deploy/vps-deploy.sh up -d --build
#
# After TLS is enabled (see deploy/request-cert.sh), publish host port 443:
#   INCLUDE_HTTPS_PORT=1 bash deploy/vps-deploy.sh up -d
#
# Override env file: ENV_FILE=/path/.env.production bash deploy/vps-deploy.sh ps

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

ENV_FILE="${ENV_FILE:-.env.production}"
args=(--env-file "$ENV_FILE" -f docker-compose.prod.yml)

if [[ "${INCLUDE_HTTPS_PORT:-}" == "1" ]]; then
  args+=(-f docker-compose.prod.https.yml)
fi

exec docker compose "${args[@]}" "$@"
