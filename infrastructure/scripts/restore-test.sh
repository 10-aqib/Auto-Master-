#!/usr/bin/env bash
# Restore test: decrypt the newest backup and restore it into a throwaway database, verify it, then drop it.
# Proves backups are restorable, not just created. Usage: infrastructure/scripts/restore-test.sh [backup-base]
set -euo pipefail
cd "$(dirname "$0")/../.."
COMPOSE="docker compose ${COMPOSE_FILES:--f docker-compose.yml}"
env_get() { grep -E "^$1=" .env | tail -1 | cut -d= -f2- || true; }
BACKUP_DIR=${BACKUP_DIR:-$(env_get BACKUP_DIR)}; BACKUP_DIR=${BACKUP_DIR:-/var/backups/webforge}
PGUSER=$(env_get POSTGRES_USER)
base=${1:-$(ls -1t "$BACKUP_DIR"/webforge-*.db.enc 2>/dev/null | head -1 | sed 's/\.db\.enc$//')}
[ -n "$base" ] && [ -f "$base.db.enc" ] || { echo "No backup found in $BACKUP_DIR" >&2; exit 2; }
run_api() { $COMPOSE run --rm -T --no-deps "$@"; }
record() { run_api api python -m webforge_api.backup record "$@" >/dev/null || true; }
psql_rc() { $COMPOSE exec -T postgres psql -U "$PGUSER" -d restore_check -tAc "$1"; }
cleanup() { $COMPOSE exec -T postgres dropdb -U "$PGUSER" --if-exists restore_check >/dev/null 2>&1 || true; }
trap 'record --kind restore_test --status failed --detail "restore-test.sh failed at line $LINENO for $(basename "$base")"; cleanup' ERR

( cd "$(dirname "$base")" && sha256sum -c "$(basename "$base").sha256" )
cleanup
$COMPOSE exec -T postgres createdb -U "$PGUSER" restore_check
run_api api python -m webforge_api.backup decrypt < "$base.db.enc" \
  | $COMPOSE exec -T postgres pg_restore -U "$PGUSER" -d restore_check --no-owner --exit-on-error
head=$(run_api api python -m webforge_api.backup check-head | tr -d '\r')
restored=$(psql_rc "SELECT version_num FROM alembic_version")
[ "$restored" = "$head" ] || { echo "migration mismatch: restored=$restored head=$head" >&2; false; }
users=$(psql_rc "SELECT count(*) FROM users")
tables=$(psql_rc "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'")
controls=$(psql_rc "SELECT count(*) FROM system_controls")
[ "$users" -ge 1 ] && [ "$tables" -ge 30 ] && [ "$controls" -ge 2 ] || { echo "restored data looks incomplete" >&2; false; }
files=$(run_api api python -m webforge_api.backup decrypt < "$base.artifacts.enc" | tar -tf - | wc -l)
cleanup
trap - ERR
detail="$(basename "$base"): head $head, $tables tables, $users users, $files artifact entries"
record --kind restore_test --status ok --detail "$detail"
echo "Restore test passed: $detail"
