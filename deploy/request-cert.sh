#!/usr/bin/env bash
# Obtain / renew a Let's Encrypt certificate using HTTP-01 via webroot.
# Prerequisites:
#   - DNS A/AAAA for TLS_DOMAIN points to this server's public IP
#   - Firewall allows TCP 80 (and 443 once HTTPS is live)
#   - Stack is up with nginx.prod.conf serving /.well-known/acme-challenge/
#
# After success:
#   1. bash deploy/render-nginx-tls.sh
#   2. Set NGINX_SITE_CONF=generated.tls.conf and Django HTTPS vars (see deploy/USAGE.txt)
#   3. INCLUDE_HTTPS_PORT=1 bash deploy/vps-deploy.sh up -d --force-recreate nginx

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

ENV_FILE="${ENV_FILE:-.env.production}"
if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing $ENV_FILE" >&2
  exit 1
fi

TLS_DOMAIN="$(grep -E '^TLS_DOMAIN=' "$ENV_FILE" | head -1 | cut -d= -f2- | tr -d '\r' | sed 's/^"\(.*\)"$/\1/' | sed "s/^'\(.*\)'$/\1/")"
LETSENCRYPT_EMAIL="$(grep -E '^LETSENCRYPT_EMAIL=' "$ENV_FILE" | head -1 | cut -d= -f2- | tr -d '\r' | sed 's/^"\(.*\)"$/\1/' | sed "s/^'\(.*\)'$/\1/")"

if [[ -z "${TLS_DOMAIN}" || -z "${LETSENCRYPT_EMAIL}" ]]; then
  echo "Set TLS_DOMAIN and LETSENCRYPT_EMAIL in $ENV_FILE" >&2
  exit 1
fi

args=(--env-file "$ENV_FILE" -f docker-compose.prod.yml --profile certbot run --rm certbot certonly
  --webroot -w /var/www/certbot
  -d "${TLS_DOMAIN}"
  --email "${LETSENCRYPT_EMAIL}"
  --agree-tos
  --non-interactive
)

# Optional: extra SAN — TLS_DOMAIN_EXTRA=api.example.com,www.example.com (comma-separated)
EXTRA="$(grep -E '^TLS_DOMAIN_EXTRA=' "$ENV_FILE" | head -1 | cut -d= -f2- | tr -d '\r' || true)"
if [[ -n "${EXTRA}" ]]; then
  IFS=',' read -ra extras <<<"${EXTRA}"
  for h in "${extras[@]}"; do
    h="$(echo "$h" | xargs)"
    [[ -n "$h" ]] && args+=(-d "$h")
  done
fi

docker compose "${args[@]}"
