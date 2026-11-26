#!/usr/bin/env bash
# Smoke-test a running local Compose stack. Usage: infrastructure/scripts/smoke.sh
set -euo pipefail

API=${SMOKE_API_URL:-http://127.0.0.1:8000}
DASH=${SMOKE_DASHBOARD_URL:-http://127.0.0.1:3000}
PREVIEW=${SMOKE_PREVIEW_URL:-http://127.0.0.1:4000}
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
check "dashboard sends CSP header"   header_has "$DASH/login" content-security-policy
check "unknown API route is 404"     status_is "$API/nope" 404
check "migrations applied (exit 0)"  bash -c '[ "$(docker compose ps -a --format "{{.ExitCode}}" migrate)" = "0" ]'
check "auth required on /auth/me"    status_is "$DASH/api/v1/auth/me" 401
check "users API requires auth"      status_is "$API/api/v1/users" 401
check "dashboard redirects to login" bash -c "[ \"\$(curl -s -o /dev/null -w '%{redirect_url}' --max-time 5 '$DASH/users')\" = '$DASH/login?next=%2Fusers' ]"
check "login page renders"           body_has "$DASH/login" "Sign in"
check "API path traversal blocked"   status_is "$DASH/api/v1/..%2F..%2Fhealth%2Flive" 404
check "preview /health/live"          body_has "$PREVIEW/health/live" '"status":"ok"'
check "preview unknown token is 404"  status_is "$PREVIEW/p/AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA/home" 404
check "preview has no API routes"     status_is "$PREVIEW/api/v1/auth/me" 404
check "preview sends sandbox CSP"     header_has "$PREVIEW/p/x/home" content-security-policy
check "worker healthy"               bash -c '[ "$(docker inspect -f "{{.State.Health.Status}}" "$(docker compose ps -q worker)")" = healthy ]'
check "postgres port not published"  not_published postgres 5432
check "redis port not published"     not_published redis 6379

exit $fail
