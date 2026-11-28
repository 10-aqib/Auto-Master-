#!/usr/bin/env bash
# Phase 4: put the WEBFORGE repository on the VM and check readiness. Does NOT create .env, build images,
# start containers or open ports. Run as the admin user (uses sudo only to create /opt/webforge):
#   bash infrastructure/vps/04-prepare-webforge.sh
# If /opt/webforge already holds the repository it only fetches and reports; it never resets or deletes.
set -euo pipefail
REPO=https://github.com/10-aqib/Auto-Master-.git
BRANCH=claude/gifted-meitner-ozj5y9
DIR=/opt/webforge
say() { printf '\n== %s\n' "$*"; }

say "1. Repository"
if [ -d "$DIR/.git" ]; then
  git -C "$DIR" fetch -q origin "$BRANCH"
  echo "  existing checkout; fetched. Local changes are kept."
elif [ -e "$DIR" ] && [ -n "$(ls -A "$DIR" 2>/dev/null)" ]; then
  echo "  $DIR exists and is not empty, and is not a git checkout. Stopping; nothing changed." >&2; exit 3
else
  sudo install -d -m 0750 -o "$(id -un)" -g "$(id -gn)" "$DIR"
  git clone -q --branch "$BRANCH" --single-branch "$REPO" "$DIR"
  echo "  cloned $BRANCH into $DIR"
fi
cd "$DIR"
echo "  branch: $(git rev-parse --abbrev-ref HEAD)  commit: $(git log -1 --format='%h %s')"
echo "  behind origin: $(git rev-list --count HEAD..origin/$BRANCH 2>/dev/null || echo ?)  local changes: $(git status --porcelain | wc -l)"

say "2. Secrets hygiene (names only; no values are printed)"
tracked=$(git ls-files | grep -E '(^|/)\.env($|\.)' | grep -v '\.env\.example$' || true)
[ -z "$tracked" ] && echo "  OK: no .env file is tracked by git" || echo "  PROBLEM: tracked env files: $tracked"
git check-ignore -q .env && echo "  OK: .env is git-ignored"
if [ -f .env ]; then
  echo "  .env present (mode $(stat -c %a .env), owner $(stat -c %U .env))"
  for kv in EMAIL_SENDING_ENABLED=false EMAIL_PROVIDER=mock EMAIL_PAUSE=true GOOGLE_PLACES_API_ENABLED=false; do
    grep -qxF "$kv" .env && echo "  OK: $kv" || echo "  REQUIRED: $kv is not set exactly"
  done
else
  echo "  .env not created yet (correct until deployment is approved). Create it later with:"
  echo "    python3 infrastructure/scripts/generate-env.py   # generates random secrets locally; review, then chmod 600"
fi
echo "  Variables in .env.example that have no default (must be supplied at deployment):"
grep -E '^[A-Z0-9_]+=$' .env.example | cut -d= -f1 | paste -sd' ' | fold -s -w 100 | sed 's/^/    /'

say "3. Resources"
mem=$(awk '/MemTotal/ {print int($2/1024)}' /proc/meminfo); swap=$(awk '/SwapTotal/ {print int($2/1024)}' /proc/meminfo)
free_gb=$(df -BG --output=avail / | tail -1 | tr -dc 0-9)
echo "  RAM ${mem} MiB, swap ${swap} MiB, free disk ${free_gb} GB, vCPUs $(nproc), arch $(uname -m)"
echo "  Needs: ~6 GB of images (browser sandbox 4.3 GB), ~10 GB extra while building, data + backups."
echo "  Measured peak memory of the whole stack at concurrency 1: ~1.1 GB (Chromium ~400 MB on test pages)."

say "4. Compose files (static check only)"
if command -v docker >/dev/null && sudo -n docker info >/dev/null 2>&1; then
  if [ -f .env ]; then
    sudo docker compose -f docker-compose.yml -f infrastructure/production/docker-compose.prod.yml config --quiet \
      && echo "  production compose config valid"
  else echo "  skipped: compose config needs .env"; fi
  echo "  published ports in production: $(grep -A4 'ports:' infrastructure/production/docker-compose.prod.yml | grep -oE '"[0-9]+:[0-9]+(/udp)?"' | paste -sd' ')"
else echo "  Docker not available yet (run 03-docker.sh first)"; fi

echo
echo "Preparation finished. Nothing was built or started; no ports were opened."
