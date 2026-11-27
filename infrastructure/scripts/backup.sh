#!/usr/bin/env bash
# Encrypted backup of PostgreSQL and the artifacts volume. Run on the host from the repository root, e.g. by a
# systemd timer (see docs/operations/runbook.md). Usage: infrastructure/scripts/backup.sh
# Env: COMPOSE_FILES (default: dev compose), BACKUP_DIR, BACKUP_KEEP_DAYS, BACKUP_S3_* via .env for off-site copy.
set -euo pipefail
umask 077
cd "$(dirname "$0")/../.."
COMPOSE="docker compose ${COMPOSE_FILES:--f docker-compose.yml}"
env_get() { grep -E "^$1=" .env | tail -1 | cut -d= -f2- || true; }
BACKUP_DIR=${BACKUP_DIR:-$(env_get BACKUP_DIR)}; BACKUP_DIR=${BACKUP_DIR:-/var/backups/webforge}
KEEP=${BACKUP_KEEP_DAYS:-$(env_get BACKUP_KEEP_DAYS)}; KEEP=${KEEP:-14}
PGUSER=$(env_get POSTGRES_USER); PGDB=$(env_get POSTGRES_DB)
[ -n "$(env_get BACKUP_ENCRYPTION_KEY)" ] || { echo "BACKUP_ENCRYPTION_KEY is not set in .env" >&2; exit 2; }
mkdir -p "$BACKUP_DIR"; chmod 700 "$BACKUP_DIR"
ts=$(date -u +%Y%m%dT%H%M%SZ); base="$BACKUP_DIR/webforge-$ts"
run_api() { $COMPOSE run --rm -T --no-deps "$@"; }
record() { run_api api python -m webforge_api.backup record "$@" >/dev/null || true; }
trap 'record --kind backup --status failed --detail "backup.sh failed at line $LINENO"; rm -f "$base".*.tmp' ERR

# 1. Database: custom-format dump, encrypted in the API container (AES-256-GCM, key never written to disk here).
$COMPOSE exec -T postgres pg_dump -U "$PGUSER" -d "$PGDB" -Fc --no-owner \
  | run_api api python -m webforge_api.backup encrypt > "$base.db.enc.tmp"
mv "$base.db.enc.tmp" "$base.db.enc"
# 2. Artifacts (screenshots, renders, PDFs): tar from a read-only mount, encrypted the same way.
run_api -v webforge_artifacts:/backup-src/artifacts:ro --entrypoint tar api -C /backup-src -cf - artifacts \
  | run_api api python -m webforge_api.backup encrypt > "$base.artifacts.enc.tmp"
mv "$base.artifacts.enc.tmp" "$base.artifacts.enc"
( cd "$BACKUP_DIR" && sha256sum "$(basename "$base").db.enc" "$(basename "$base").artifacts.enc" > "$(basename "$base").sha256" )
bytes=$(( $(stat -c %s "$base.db.enc") + $(stat -c %s "$base.artifacts.enc") ))
digest=$(sha256sum "$base.db.enc" | cut -d' ' -f1)

# 3. Off-site copy when configured (S3-compatible, server-side encrypted on top of our own encryption).
location="local:$base"
if [ -n "$(env_get BACKUP_S3_BUCKET)" ]; then
  for f in "$base.db.enc" "$base.artifacts.enc" "$base.sha256"; do
    run_api -v "$BACKUP_DIR:$BACKUP_DIR:ro" api python -m webforge_api.backup upload "$f" >/dev/null
  done
  location="s3:$(env_get BACKUP_S3_BUCKET)/$(env_get BACKUP_S3_PREFIX)$(basename "$base")"
else
  echo "WARNING: BACKUP_S3_BUCKET not set; this backup exists only on this server." >&2
fi
record --kind backup --status ok --bytes "$bytes" --sha256 "$digest" --location "$location" --detail "$(basename "$base")"
# 4. Local retention.
find "$BACKUP_DIR" -name 'webforge-*' -type f -mtime +"$KEEP" -delete
echo "Backup complete: $base.{db,artifacts}.enc ($bytes bytes) -> $location"
