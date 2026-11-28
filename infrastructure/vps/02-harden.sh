#!/usr/bin/env bash
# Phase 2: Ubuntu 24.04 hardening for the WEBFORGE VM.
# DRY RUN by default (prints every action). Changes are made only with --apply, after owner approval:
#   sudo bash infrastructure/vps/02-harden.sh            # dry run
#   sudo bash infrastructure/vps/02-harden.sh --apply    # apply
#   sudo bash infrastructure/vps/02-harden.sh --apply --swap 2G   # also create a swap file (if none exists)
# Keep your current SSH session open until a NEW session has been tested.
# It never opens ports 80/443 (deployment is not authorised), never touches Google Cloud firewall rules,
# the guest agent or OS Login, and never removes packages, files or other projects.
set -euo pipefail
APPLY=0; SWAP=""
while [ $# -gt 0 ]; do case "$1" in --apply) APPLY=1;; --swap) SWAP=${2:?size, e.g. 2G}; shift;; *) echo "unknown option $1" >&2; exit 2;; esac; shift; done
[ "$(id -u)" = 0 ] || { echo "Run with sudo." >&2; exit 2; }
. /etc/os-release; [ "$ID" = ubuntu ] && [ "$VERSION_ID" = "24.04" ] || { echo "Expected Ubuntu 24.04, found $PRETTY_NAME. Stopping." >&2; exit 3; }
ADMIN=${SUDO_USER:-}; [ -n "$ADMIN" ] && [ "$ADMIN" != root ] || { echo "Run via sudo from your admin account (not as root)." >&2; exit 2; }
STAMP=$(date -u +%Y%m%dT%H%M%SZ); BK=/var/backups/webforge-vps-$STAMP
export DEBIAN_FRONTEND=noninteractive NEEDRESTART_MODE=l  # list services needing restart; never auto-restart others
say() { printf '\n== %s\n' "$*"; }
run() { if [ $APPLY = 1 ]; then echo "+ $*"; "$@"; else echo "[dry-run] $*"; fi; }
put() {  # put <path> <content>: back up any existing file, then write
  local path=$1 content=$2
  if [ $APPLY = 1 ]; then
    [ -e "$path" ] && { mkdir -p "$BK$(dirname "$path")"; cp -a "$path" "$BK$path"; echo "  backed up $path -> $BK$path"; }
    printf '%s\n' "$content" > "$path"; echo "+ wrote $path"
  else echo "[dry-run] write $path:"; printf '%s\n' "$content" | sed 's/^/    /'; fi
}

say "0. Preconditions"
SSH_PORT=$(sshd -T 2>/dev/null | awk '/^port /{print $2; exit}'); SSH_PORT=${SSH_PORT:-22}
AKC=$(sshd -T 2>/dev/null | awk '/^authorizedkeyscommand /{print $2}')
KEYS=$(grep -cvE '^\s*(#|$)' "/home/$ADMIN/.ssh/authorized_keys" 2>/dev/null) || true; KEYS=${KEYS:-0}
echo "  admin=$ADMIN ssh_port=$SSH_PORT authorized_keys=$KEYS oslogin_command=${AKC:-none}"
SSH_OK=1
if [ "$KEYS" = 0 ] && { [ -z "$AKC" ] || [ "$AKC" = none ]; }; then
  SSH_OK=0; echo "  WARNING: no key-based login found for $ADMIN; SSH settings will NOT be changed."
fi

say "1. Update packages (upgrade only; nothing is removed)"
run apt-get update -q
run apt-get -y -q -o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold upgrade

say "2. Essential utilities"
run apt-get -y -q install ca-certificates curl gnupg git jq htop ncdu unzip ufw fail2ban python3-systemd \
  unattended-upgrades apt-listchanges

say "3. Unattended security updates (security pocket only, Ubuntu default; no automatic reboot)"
put /etc/apt/apt.conf.d/20auto-upgrades 'APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
APT::Periodic::AutocleanInterval "7";'
run systemctl enable --now unattended-upgrades
[ $APPLY = 1 ] && unattended-upgrade --dry-run -d 2>&1 | grep -E "Allowed origins" | head -1 | sed 's/^/  /' || true

say "4. Fail2ban for SSH (systemd journal backend)"
put /etc/fail2ban/jail.d/webforge-sshd.local "[sshd]
enabled  = true
port     = $SSH_PORT
backend  = systemd
# Ubuntu 24.04 names the unit ssh.service (the stock filter watches sshd.service and would see nothing).
journalmatch = _SYSTEMD_UNIT=ssh.service + _COMM=sshd
# With keys only, failed logins show up as 'Connection closed by authenticating user ... [preauth]'.
mode     = aggressive
maxretry = 5
findtime = 10m
bantime  = 1h
# 35.235.240.0/20 is Google Cloud IAP TCP forwarding (browser SSH), never banned.
ignoreip = 127.0.0.1/8 ::1 35.235.240.0/20"
run systemctl enable fail2ban
run systemctl restart fail2ban
[ $APPLY = 1 ] && { sleep 2; fail2ban-client status sshd | sed 's/^/  /'; } || true

say "5. SSH hardening (keys only, no root login). Existing sessions are not dropped."
SSHD_DROPIN=/etc/ssh/sshd_config.d/10-webforge-hardening.conf  # 10- sorts first; sshd uses the first value it reads
if [ $SSH_OK = 1 ]; then
  put $SSHD_DROPIN "# WEBFORGE hardening ($STAMP). Remove this file and reload ssh to undo.
PermitRootLogin no
PasswordAuthentication no
KbdInteractiveAuthentication no
PubkeyAuthentication yes
MaxAuthTries 4
LoginGraceTime 30
X11Forwarding no"
  if [ $APPLY = 1 ]; then
    if sshd -t; then
      if systemctl is-active --quiet ssh; then systemctl reload ssh && echo "  sshd config valid; reloaded"
      else echo "  sshd config valid; ssh is socket-activated, so new connections use it"; fi
    else echo "  sshd -t FAILED; removing $SSHD_DROPIN"; rm -f $SSHD_DROPIN; sshd -t; fi
    sshd -T | grep -Ei '^(permitrootlogin|passwordauthentication|kbdinteractiveauthentication|maxauthtries) ' | sed 's/^/  /'
  fi
else echo "  skipped (see precondition warning)"; fi

say "6. UFW host firewall: allow SSH first, deny other inbound, allow outbound"
run ufw allow "$SSH_PORT/tcp" comment 'SSH'
run ufw default deny incoming
run ufw default allow outgoing
if [ $APPLY = 1 ]; then
  ufw show added | grep -q "$SSH_PORT/tcp" || { echo "  SSH rule missing; NOT enabling UFW" >&2; exit 4; }
  ufw --force enable; ufw status verbose | sed 's/^/  /'
else echo "[dry-run] ufw --force enable   (only after the SSH rule is confirmed)"; fi
echo "  Ports 80/443 stay closed until deployment is approved (then: ufw allow 80,443/tcp)."
echo "  Docker-published ports bypass UFW: WEBFORGE binds dev ports to 127.0.0.1 and publishes only 80/443 (Caddy) in production."

if [ -n "$SWAP" ]; then
  say "7. Swap file ($SWAP)"
  if [ -n "$(swapon --show)" ]; then echo "  swap already present; unchanged"
  else
    if [ -e /swapfile ]; then echo "  /swapfile exists but is not active; left unchanged (check it manually)"
    elif [ $APPLY = 1 ]; then
      if fallocate -l "$SWAP" /swapfile && chmod 600 /swapfile && mkswap /swapfile >/dev/null && swapon /swapfile; then
        mkdir -p "$BK/etc"; cp -a /etc/fstab "$BK/etc/fstab"
        grep -q '^/swapfile ' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
        put /etc/sysctl.d/60-webforge-swap.conf 'vm.swappiness=10'
        sysctl -q -p /etc/sysctl.d/60-webforge-swap.conf; swapon --show | sed 's/^/  /'
      else
        echo "  WARNING: swap could not be enabled on this filesystem; removed the new /swapfile and continued"
        swapoff /swapfile 2>/dev/null || true; rm -f /swapfile
      fi
    else
      echo "[dry-run] create /swapfile ($SWAP, mode 600), mkswap, swapon, add to /etc/fstab (backed up), vm.swappiness=10"
    fi
  fi
fi

say "Summary"
[ $APPLY = 1 ] && echo "  Applied. Backups of changed files: $BK" || echo "  Dry run only. Nothing was changed. Re-run with --apply after approval."
[ -f /var/run/reboot-required ] && echo "  A reboot is required to finish updates (not done automatically)." || true
echo "  NOW: open a NEW SSH session and confirm you can log in before closing this one."
