#!/usr/bin/env bash
# Smoke-test a running local Compose stack. Usage: infrastructure/scripts/smoke.sh
set -euo pipefail

API=${SMOKE_API_URL:-http://127.0.0.1:8000}
DASH=${SMOKE_DASHBOARD_URL:-http://127.0.0.1:3000}
fail=0

check() {
  local name=$1; shift
  if "$@"; then echo "PASS  $name"; else echo "FAIL  $name"; fail=1; fi
}

# Fetch the body first: piping curl into `grep -q` can SIGPIPE curl and trip pipefail.
fetch() { curl -fsS --max-time 10 "$1"; }
body_has() { local b; b=$(fetch "$1") && grep -qF -- "$2" <<<"$b"; }
body_matches() { local b; b=$(fetch "$1") && grep -qE -- "$2" <<<"$b"; }
status_is() { [ "$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "$1")" = "$2" ]; }
# `docker compose port` prints ":0" (or nothing) when a container port is not published.
not_published() { local out; out=$(docker compose port "$1" "$2" 2>/dev/null || true); [ -z "$out" ] || [ "$out" = ":0" ]; }
header_has() { local h; h=$(curl -sS -o /dev/null -D - --max-time 5 "$1") && grep -qi "^$2:" <<<"$h"; }

check "api /health/live"             body_has "$API/health/live" '"status":"ok"'
check "api /health/ready is ready"   body_has "$API/health/ready" '"status":"ready"'
check "api returns x-request-id"     header_has "$API/health/live" x-request-id
check "dashboard /health"            body_has "$DASH/health" '"status":"ok"'
# The status panel streams in after the shell, as HTML (>Ready<) or RSC payload ("Ready\").
check "dashboard shows API ready"    body_matches "$DASH/" '(>Ready<|"Ready\\")'
check "dashboard sends CSP header"   header_has "$DASH/" content-security-policy
check "unknown API route is 404"     status_is "$API/nope" 404
check "postgres port not published"  not_published postgres 5432
check "redis port not published"     not_published redis 6379

exit $fail
