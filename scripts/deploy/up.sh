#!/usr/bin/env bash
# Build, migrate, start and health-check the stack. Run from anywhere on the server; safe to
# re-run for every update:  git pull && bash scripts/deploy/up.sh
set -euo pipefail

cd "$(dirname "$0")/../.."
ROOT="$(pwd)"
ENV_FILE="${ENV_FILE:-.env.prod}"

if [ ! -f "$ENV_FILE" ]; then
  echo "$ENV_FILE missing: run scripts/deploy/bootstrap.sh first" >&2
  exit 1
fi
if grep -q -E '__GENERATE__|FILL-IN|you@example\.com|your\.address@gmail\.com|xxxx-xxxx' "$ENV_FILE"; then
  echo "$ENV_FILE still has placeholders:" >&2
  grep -n -E '__GENERATE__|FILL-IN|you@example\.com|your\.address@gmail\.com|xxxx-xxxx' "$ENV_FILE" >&2
  exit 1
fi

compose() {
  docker compose --env-file "$ENV_FILE" -f infra/docker-compose.yml -f infra/docker-compose.prod.yml "$@"
}

DOMAIN="$(grep -E '^DOMAIN=' "$ENV_FILE" | cut -d= -f2-)"

echo "==> Building images (first time takes several minutes)"
compose build

echo "==> Starting databases and storage"
compose up -d postgres redis storage storage-init

echo "==> Waiting for postgres"
for _ in $(seq 1 60); do
  [ "$(compose ps --format '{{.Health}}' postgres)" = "healthy" ] && break
  sleep 2
done

# On a fresh volume postgres' init script has already created roles; this refreshes them and
# is idempotent (same as `just db-roles`).
echo "==> Database roles"
compose exec -T postgres sh /opt/roles/roles.sh

echo "==> Migrations (core, then ai)"
compose run --rm core-migrate uv run --no-sync alembic upgrade head
compose run --rm --no-deps ai-service uv run --no-sync alembic upgrade head

echo "==> Starting everything"
compose up -d

echo "==> Health check (https://$DOMAIN/api/health)"
ok=0
for i in $(seq 1 60); do
  if curl -fsS --max-time 5 "https://$DOMAIN/api/health" >/dev/null 2>&1; then
    ok=1
    break
  fi
  sleep 5
done

compose ps
if [ "$ok" -eq 1 ]; then
  echo
  echo "UP: https://$DOMAIN"
else
  echo
  echo "Not healthy after 5 minutes. Look at: docker compose --env-file $ENV_FILE -f infra/docker-compose.yml -f infra/docker-compose.prod.yml logs --tail 100 caddy web core-api" >&2
  echo "(first HTTPS request can fail while Caddy fetches its certificate; see infra/DEPLOY.md troubleshooting)" >&2
  exit 1
fi
echo "Repo: $ROOT"
