#!/usr/bin/env bash
# Phase 3: Docker Engine + Compose plugin from Docker's official apt repository (Ubuntu 24.04).
# DRY RUN by default; changes only with --apply, after owner approval:
#   sudo bash infrastructure/vps/03-docker.sh            # dry run
#   sudo bash infrastructure/vps/03-docker.sh --apply
# Never removes packages: if a conflicting package (docker.io, podman-docker, ...) is installed it stops and reports.
# Does not add anyone to the docker group (that is root-equivalent); use sudo docker, or decide that separately.
set -euo pipefail
APPLY=0; [ "${1:-}" = --apply ] && APPLY=1
[ "$(id -u)" = 0 ] || { echo "Run with sudo." >&2; exit 2; }
. /etc/os-release; [ "$ID" = ubuntu ] && [ "$VERSION_ID" = "24.04" ] || { echo "Expected Ubuntu 24.04, found $PRETTY_NAME." >&2; exit 3; }
CODENAME=${UBUNTU_CODENAME:-$VERSION_CODENAME}; ARCH=$(dpkg --print-architecture)
DOCKER_FPR=9DC858229FC7DD38854AE2D88D81803C0EBFCD88   # Docker's published release key fingerprint
say() { printf '\n== %s\n' "$*"; }
run() { if [ $APPLY = 1 ]; then echo "+ $*"; "$@"; else echo "[dry-run] $*"; fi; }

say "1. Conflicting packages"
conflicts=""
for p in docker.io docker-doc docker-compose docker-compose-v2 podman-docker containerd runc; do
  dpkg-query -W -f='${Status}' "$p" 2>/dev/null | grep -q 'install ok installed' && conflicts="$conflicts $p"
done
if [ -n "$conflicts" ]; then
  echo "  Installed:$conflicts. Docker's packages conflict with these. Nothing changed."
  echo "  Check that no other project uses them; then remove with approval: sudo apt-get remove$conflicts"; exit 5
fi
echo "  none"

say "2. Docker apt repository (signed-by key, fingerprint checked)"
run apt-get update -q
run apt-get -y -q install ca-certificates curl gnupg
if [ $APPLY = 1 ]; then
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /tmp/docker.asc
  fpr=$(gpg --show-keys --with-colons /tmp/docker.asc | awk -F: '/^fpr/{print $10; exit}')
  [ "$fpr" = "$DOCKER_FPR" ] || { echo "  Key fingerprint mismatch ($fpr). Stopping." >&2; rm -f /tmp/docker.asc; exit 6; }
  install -m 0644 /tmp/docker.asc /etc/apt/keyrings/docker.asc; rm -f /tmp/docker.asc
  echo "  key OK ($fpr)"
  printf 'Types: deb\nURIs: https://download.docker.com/linux/ubuntu\nSuites: %s\nComponents: stable\nArchitectures: %s\nSigned-By: /etc/apt/keyrings/docker.asc\n' \
    "$CODENAME" "$ARCH" > /etc/apt/sources.list.d/docker.sources
  echo "+ wrote /etc/apt/sources.list.d/docker.sources ($CODENAME, $ARCH)"
else
  echo "[dry-run] download https://download.docker.com/linux/ubuntu/gpg, require fingerprint $DOCKER_FPR"
  echo "[dry-run] write /etc/apt/sources.list.d/docker.sources (suite $CODENAME, arch $ARCH)"
fi
run apt-get update -q

say "3. Install Docker Engine, CLI, containerd, Buildx and Compose plugins"
run apt-get -y -q install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

say "4. Log rotation (daemon default for new containers; WEBFORGE's compose file also caps each service)"
DAEMON=/etc/docker/daemon.json
if [ -s $DAEMON ]; then echo "  $DAEMON already exists; NOT changed. Contents:"; sed 's/^/    /' $DAEMON
elif [ $APPLY = 1 ]; then
  mkdir -p /etc/docker
  printf '{\n  "log-driver": "local",\n  "log-opts": { "max-size": "10m", "max-file": "3" },\n  "live-restore": true\n}\n' > $DAEMON
  echo "+ wrote $DAEMON"
else echo '[dry-run] write /etc/docker/daemon.json: local log driver, 10m x 3 files, live-restore'; fi

say "5. Start at boot"
run systemctl enable --now containerd docker
[ $APPLY = 1 ] && systemctl restart docker

say "6. Verify"
if [ $APPLY = 1 ]; then
  echo "  enabled: docker=$(systemctl is-enabled docker) containerd=$(systemctl is-enabled containerd)"
  docker version --format '  engine {{.Server.Version}} ({{.Server.Os}}/{{.Server.Arch}})'
  docker compose version | sed 's/^/  /'
  docker buildx version | sed 's/^/  /'
  echo "  log driver: $(docker info --format '{{.LoggingDriver}}')  storage: $(docker info --format '{{.Driver}}')"
  docker run --rm hello-world 2>&1 | grep -m1 'Hello from Docker' | sed 's/^/  /' \
    || { echo "  FAILED: Docker is installed but cannot run a test container. Check: journalctl -u docker" >&2; exit 8; }
  echo "  platform: $(uname -m). All WEBFORGE base images publish linux/amd64 and linux/arm64."
  echo "  Docker data: $(docker info --format '{{.DockerRootDir}}'), free: $(df -h --output=avail /var/lib/docker | tail -1)"
else echo "  [dry-run] docker version, docker compose version, hello-world, log driver check"; fi
echo
[ $APPLY = 1 ] && echo "Docker installed." || echo "Dry run only. Nothing was changed."
