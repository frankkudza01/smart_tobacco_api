#!/usr/bin/env bash
# Renewal hook for cron (e.g. weekly): renew certs and reload nginx.
# Crontab example:
#   0 4 * * * cd /opt/backend && bash deploy/renew-certs.sh >> /var/log/certbot-renew.log 2>&1

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

ENV_FILE="${ENV_FILE:-.env.production}"

docker compose --env-file "$ENV_FILE" -f docker-compose.prod.yml --profile certbot run --rm certbot renew --webroot -w /var/www/certbot

# Reload nginx so renewed certs are picked up (short downtime-free for reload).
docker compose --env-file "$ENV_FILE" -f docker-compose.prod.yml exec -T nginx nginx -s reload
