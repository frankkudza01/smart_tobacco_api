#!/usr/bin/env bash
# Runs the equivalent of `npm run deploy:local` against the Docker Hardhat node (`hardhat` service).
# Requires the stack with profile `blockchain` (Hardhat container running).
#
# VPS / production files:
#   COMPOSE_PROFILES=blockchain bash deploy/vps-deploy.sh up -d --build
#   bash deploy/deploy-hardhat-contract.sh
#
# Local Docker dev:
#   COMPOSE_PROFILES=blockchain docker compose --env-file .env -f docker-compose.yml up -d --build
#   COMPOSE_FILE=docker-compose.yml ENV_FILE=.env bash deploy/deploy-hardhat-contract.sh

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

ENV_FILE="${ENV_FILE:-.env.production}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"

compose_args=(--env-file "$ENV_FILE" -f "$COMPOSE_FILE")

if [[ "${INCLUDE_HTTPS_PORT:-}" == "1" && "${COMPOSE_FILE}" == "docker-compose.prod.yml" ]]; then
  compose_args+=(-f docker-compose.prod.https.yml)
fi

docker compose "${compose_args[@]}" --profile blockchain run --rm --no-deps \
  -e HARDHAT_RPC_URL=http://hardhat:8545 \
  -e HARDHAT_DEPLOYMENT_JSON_OUT=/artifact/deployment-docker.json \
  -v "$ROOT/hardhat:/artifact:rw" \
  hardhat \
  npx hardhat run scripts/deploy.js --network docker
