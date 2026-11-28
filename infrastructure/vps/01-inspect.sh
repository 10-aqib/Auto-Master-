#!/usr/bin/env bash
# Phase 1: READ-ONLY inspection of a Compute Engine VM before WEBFORGE AI is installed.
# Changes nothing, installs nothing, prints no secrets. Run as the admin user:
#   bash infrastructure/vps/01-inspect.sh | tee ~/webforge-inspect.txt
# (If the repository is not on the server yet: curl -fsSL <raw URL of this file> -o inspect.sh, read it, then run.)
set -uo pipefail
export LC_ALL=C
S() { sudo -n "$@" 2>/dev/null || echo "  (needs sudo; skipped)"; }
h() { printf '\n== %s\n' "$*"; }
md() { curl -fs -m 2 -H 'Metadata-Flavor: Google' "http://metadata.google.internal/computeMetadata/v1/$1" 2>/dev/null || echo "(unavailable)"; }

h "Operating system"
. /etc/os-release; echo "  $PRETTY_NAME (id=$ID version=$VERSION_ID)"
echo "  kernel $(uname -r), arch $(uname -m)"
[ "$ID" = ubuntu ] && [ "$VERSION_ID" = "24.04" ] && echo "  OK: Ubuntu 24.04 LTS" || echo "  WARNING: not Ubuntu 24.04 LTS"
echo "  uptime: $(uptime -p)"
[ -f /var/run/reboot-required ] && echo "  NOTE: a reboot is pending" || true

h "Compute Engine metadata (read-only)"
echo "  machine type: $(md instance/machine-type | awk -F/ '{print $NF}')"
echo "  zone:         $(md instance/zone | awk -F/ '{print $NF}')"
echo "  external IP:  $(md instance/network-interfaces/0/access-configs/0/external-ip)"
echo "  internal IP:  $(md instance/network-interfaces/0/ip)"
echo "  network tags: $(md instance/tags | tr -d '\n')"
echo "  OS Login:     project=$(md project/attributes/enable-oslogin) instance=$(md instance/attributes/enable-oslogin)"

h "CPU and memory"
echo "  vCPUs: $(nproc)  model: $(grep -m1 'model name' /proc/cpuinfo | cut -d: -f2 | xargs)"
free -m | sed 's/^/  /'
swapon --show=NAME,SIZE,USED 2>/dev/null | sed 's/^/  /' || true
[ -z "$(swapon --show 2>/dev/null)" ] && echo "  swap: none"

h "Disk"
df -h -x tmpfs -x devtmpfs -x squashfs -x overlay | sed 's/^/  /'
lsblk -d -o NAME,SIZE,TYPE,MODEL | sed 's/^/  /'

h "Users with a login shell, and sudo membership"
awk -F: '$7 !~ /(nologin|false|sync)$/ {print "  " $1 " (uid " $3 ", home " $6 ")"}' /etc/passwd
echo "  sudo group: $(getent group sudo | cut -d: -f4)"
echo "  google-sudoers: $(getent group google-sudoers | cut -d: -f4)"
echo "  current user: $(id -un) groups: $(id -Gn)"
echo "  logged in now:"; who | sed 's/^/    /'

h "SSH server (effective settings that matter)"
if sudo -n true 2>/dev/null; then
  sudo sshd -T 2>/dev/null | grep -Ei '^(port|permitrootlogin|passwordauthentication|kbdinteractiveauthentication|pubkeyauthentication|authorizedkeyscommand|maxauthtries|x11forwarding|allowtcpforwarding|allowusers|allowgroups|usepam) ' | sed 's/^/  /'
  echo "  drop-in files: $(ls /etc/ssh/sshd_config.d/ 2>/dev/null | tr '\n' ' ')"
else echo "  (needs sudo; skipped)"; fi
keys=$(grep -cvE '^\s*(#|$)' ~/.ssh/authorized_keys 2>/dev/null) || true
echo "  authorized keys for $(id -un): ${keys:-0} (key contents not shown)"

h "Firewall (host). Note: Google Cloud VPC firewall rules apply in front of this and are not visible here"
S ufw status verbose | sed 's/^/  /'
echo "  nftables/iptables rule count: $(sudo -n nft list ruleset 2>/dev/null | grep -c . || echo '(needs sudo)')"

h "Listening sockets"
S ss -tulpnH | awk '{printf "  %-5s %-28s %s\n", $1, $5, $7}'

h "Running services"
systemctl list-units --type=service --state=running --no-legend --plain | awk '{print "  " $1}'

h "Relevant packages"
for p in docker-ce docker.io docker-compose-plugin podman containerd runc fail2ban ufw unattended-upgrades git curl nginx apache2 caddy postgresql redis-server nodejs google-guest-agent; do
  v=$(dpkg-query -W -f='${Status} ${Version}' "$p" 2>/dev/null | grep '^install ok installed' | awk '{print $4}')
  [ -n "$v" ] && echo "  $p $v"
done
echo "  upgradable packages: $(apt list --upgradable 2>/dev/null | grep -c upgradable)"
echo "  unattended-upgrades: $(cat /etc/apt/apt.conf.d/20auto-upgrades 2>/dev/null | tr '\n' ' ' || echo 'not configured')"

h "Other projects on this server (report only; nothing is changed)"
ls -d /opt/* /srv/* /var/www/* 2>/dev/null | sed 's/^/  /' || true
pgrep -a -f -i 'firebase|node|python|gunicorn|uvicorn' 2>/dev/null | cut -c1-120 | sed 's/^/  /' || true
command -v docker >/dev/null && { echo "  docker containers:"; S docker ps --format '    {{.Names}} {{.Image}} {{.Status}} {{.Ports}}'; }

h "WEBFORGE requirements check"
mem=$(awk '/MemTotal/ {print int($2/1024)}' /proc/meminfo); swap=$(awk '/SwapTotal/ {print int($2/1024)}' /proc/meminfo)
free_gb=$(df -BG --output=avail / | tail -1 | tr -dc 0-9)
echo "  RAM ${mem} MiB, swap ${swap} MiB, free disk on / ${free_gb} GB, vCPUs $(nproc), arch $(uname -m)"
[ "$mem" -ge 3800 ] && echo "  RAM: comfortable" || { [ "$mem" -ge 1900 ] && echo "  RAM: tight; needs 2 GB swap and worker concurrency 1" || echo "  RAM: INSUFFICIENT for the full stack"; }
[ "$free_gb" -ge 20 ] && echo "  Disk: OK" || echo "  Disk: INSUFFICIENT (need >= 20 GB free: ~6 GB images, build cache, data, backups)"
case "$(uname -m)" in x86_64|aarch64) echo "  Architecture: supported (all images are amd64 + arm64)";; *) echo "  Architecture: UNSUPPORTED";; esac
for port in 80 443; do ss -tlnH "sport = :$port" | grep -q . && echo "  Port $port: IN USE (conflict for Caddy)" || echo "  Port $port: free"; done
echo
echo "Inspection finished. Nothing was changed."
