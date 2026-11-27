#!/usr/bin/env bash
# Emergency recovery: rebuild the database and artifacts volume from an encrypted backup onto an EMPTY stack
# (new server, or after the volumes were lost). Refuses to overwrite existing data. Leaves the global and email
# pauses ON so nothing resumes until the owner has checked the system.
# Usage: infrastructure/scripts/recover.sh [backup-base]   (set COMPOSE_FILES for production)
set -euo pipefail
cd "$(dirname "$0")/../.."
COMPOSE="docker compose ${COMPOSE_FILES:--f docker-compose.yml}"
env_get() { grep -E "^$1=" .env | tail -1 | cut -d= -f2- || true; }
BACKUP_DIR=${BACKUP_DIR:-$(env_get BACKUP_DIR)}; BACKUP_DIR=${BACKUP_DIR:-/var/backups/webforge}
PGUSER=$(env_get POSTGRES_USER); PGDB=$(env_get POSTGRES_DB); PGDB=${PGDB:-webforge}
base=${1:-$(ls -1t "$BACKUP_DIR"/webforge-*.db.enc 2>/dev/null | head -1 | sed 's/\.db\.enc$//')}
[ -n "$base" ] && [ -f "$base.db.enc" ] && [ -f "$base.artifacts.enc" ] || { echo "No complete backup found in $BACKUP_DIR" >&2; exit 2; }
run_api() { $COMPOSE run --rm -T --no-deps "$@"; }
psql_main() { $COMPOSE exec -T postgres psql -U "$PGUSER" -d "$PGDB" -tAc "$1"; }

echo "1/6 Checking backup integrity: $(basename "$base")"
( cd "$(dirname "$base")" && sha256sum -c --quiet "$(basename "$base").sha256" )

echo "2/6 Starting PostgreSQL and Redis only"
$COMPOSE up -d --wait postgres redis

echo "3/6 Refusing to overwrite existing data"
tables=$(psql_main "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'")
[ "$tables" = "0" ] || { echo "Database $PGDB already has $tables tables. Recover only onto an empty database." >&2; exit 3; }
existing=$(run_api --entrypoint sh api -c 'find /data/artifacts -mindepth 1 | wc -l' | tr -d '\r')
[ "$existing" = "0" ] || { echo "Artifacts volume is not empty ($existing entries). Recover only onto an empty volume." >&2; exit 3; }

echo "4/6 Restoring the database"
run_api api python -m webforge_api.backup decrypt < "$base.db.enc" \
  | $COMPOSE exec -T postgres pg_restore -U "$PGUSER" -d "$PGDB" --no-owner --exit-on-error
run_api api python -m webforge_api.cli migrate  # a backup from an older release is brought to the current head

echo "5/6 Restoring artifacts"
run_api api python -m webforge_api.backup decrypt < "$base.artifacts.enc" \
  | run_api --entrypoint tar api -C /data -xf - --no-same-owner

echo "6/6 Pausing everything until the owner has reviewed the recovered system"
run_api api python -m webforge_api.cli emergency-pause --reason "Recovered from $(basename "$base"); review before resuming."
run_api api python -m webforge_api.backup record --kind restore_test --status ok \
  --detail "full recovery from $(basename "$base")" >/dev/null || true

echo "Recovery complete. Next: start the stack (make up / make prod-up), run make smoke, check Operations, then resume"
echo "pauses from Settings only when everything looks right."
