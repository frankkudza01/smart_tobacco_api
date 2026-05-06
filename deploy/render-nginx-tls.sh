#!/usr/bin/env bash
# Builds docker/nginx/generated.tls.conf from docker/nginx/nginx.tls.conf.template.
# Requires TLS_DOMAIN in .env.production (FQDN that matches your Let's Encrypt certificate).

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

ENV_FILE="${ENV_FILE:-.env.production}"
if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing $ENV_FILE" >&2
  exit 1
fi

# Strip CRLF and quotes; ignore comments.
TLS_DOMAIN="$(grep -E '^TLS_DOMAIN=' "$ENV_FILE" | head -1 | cut -d= -f2- | tr -d '\r' | sed 's/^"\(.*\)"$/\1/' | sed "s/^'\(.*\)'$/\1/")"
if [[ -z "${TLS_DOMAIN}" ]]; then
  echo "Set TLS_DOMAIN=api.example.com in $ENV_FILE" >&2
  exit 1
fi

TEMPLATE="$ROOT/docker/nginx/nginx.tls.conf.template"
OUT="$ROOT/docker/nginx/generated.tls.conf"

sed "s/__TLS_DOMAIN__/${TLS_DOMAIN}/g" "$TEMPLATE" >"$OUT"
echo "Wrote $OUT"
