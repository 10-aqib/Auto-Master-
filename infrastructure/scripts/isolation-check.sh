#!/usr/bin/env bash
# Prove from INSIDE the running browser sandbox that it cannot reach internal services,
# cloud metadata or the internet directly, that the egress proxy refuses internal targets,
# and that the sandbox holds no secrets. Exit 1 on any failure.
set -euo pipefail
fail=0
check() { if "$@"; then echo "PASS  $name"; else echo "FAIL  $name"; fail=1; fi; }

report=$(docker compose exec -T browser python -c "import asyncio,json,os; from webforge_browser.selftest import run_selftest; print(json.dumps(asyncio.run(run_selftest(os.environ.get('EGRESS_PROXY_URL')))))")
echo "$report" | python3 -m json.tool

field() { python3 -c "import json,sys; print(json.loads(sys.argv[1])$2)" "$report"; }
name="sandbox reports isolated";            check [ "$(field "$report" "['isolated']")" = "True" ]
name="no direct TCP to db/redis/api/metadata/internet"; check [ "$(field "$report" "['direct_connections_blocked']")" = "True" ]
name="egress proxy refuses internal targets"; check [ "$(field "$report" "['proxy_denies_internal']")" = "True" ]
name="no secrets in sandbox environment";   check [ "$(field "$report" "['env_has_no_secrets']")" = "True" ]
name="sandbox cannot resolve postgres";     check bash -c '! docker compose exec -T browser python -c "import socket; socket.gethostbyname(\"postgres\")" 2>/dev/null'
name="sandbox has no published ports";      check bash -c '[ -z "$(docker compose port browser 9000 2>/dev/null | grep -v ^:0)" ]'
name="sandbox runs as non-root";            check bash -c '[ "$(docker compose exec -T browser id -u)" != "0" ]'
name="sandbox filesystem is read-only";     check bash -c '! docker compose exec -T browser sh -c "touch /app/x" 2>/dev/null'
exit $fail
