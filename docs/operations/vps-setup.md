# Compute Engine VPS Setup — Report and Runbook

Date: 2026-11-28 · Branch `claude/gifted-meitner-ozj5y9` · Deployment: **NOT authorised**.

## 0. Status at a glance

| Phase | Status |
|---|---|
| 1. Inspect the server | **Not run on the VM.** The cloud session that prepared this had no SSH access to it (no key or SSH config, and no valid Google Cloud credentials). The read-only script is ready: `infrastructure/vps/01-inspect.sh` |
| 2. Secure Ubuntu | Script ready and **tested on Ubuntu 24.04 with systemd** (`02-harden.sh`). Not applied to the VM |
| 3. Install Docker | Script ready and tested (`03-docker.sh`). Not applied to the VM |
| 4. Prepare WEBFORGE | Script ready and tested (`04-prepare-webforge.sh`); resource analysis done (§4) |
| 5. Readiness checks | Repository-side checks done (§5); VM-side checks run by the scripts |

The VM facts in §1 must come from `01-inspect.sh`. Nothing below is assumed about your VM.

## 1. VPS specifications (fill from `01-inspect.sh`)

| Item | Value |
|---|---|
| OS (must be Ubuntu 24.04 LTS) | _from inspection_ |
| Machine type / vCPU / RAM | _from inspection_ |
| Boot disk size / free | _from inspection_ |
| External IP (ephemeral or static) | _from inspection_ |
| Swap | _from inspection_ |
| Existing services and ports (Firebase-related or other) | _from inspection; nothing is changed_ |

## 2. Scripts (all in `infrastructure/vps/`)

Every script is read-only, or a dry run unless `--apply` is given. Each one verifies its result and backs up any
file it changes to `/var/backups/webforge-vps-<timestamp>/`. None of them:
- touches Google Cloud resources, firewall rules, OS Login or the guest agent;
- removes packages, files or volumes;
- opens ports 80/443;
- creates `.env` or starts WEBFORGE.

| Script | What it does | Verified in testing |
|---|---|---|
| `01-inspect.sh` | OS/CPU/RAM/disk/metadata (machine type, zone, IPs, OS Login), users, sudoers, effective sshd settings, UFW, listening ports, services, packages, other projects, WEBFORGE fit check | Ran on Ubuntu 24.04 as a sudo user |
| `02-harden.sh [--apply] [--swap 2G]` | apt upgrade (never removes); utilities; unattended **security** updates (no auto-reboot); Fail2ban for SSH; SSH drop-in (no root, no passwords, MaxAuthTries 4, no X11); UFW (SSH allowed *before* enabling, then deny inbound); optional swap | Applied twice (idempotent). After hardening: **new key login OK, password login refused, root login refused, sudo OK**. Fail2ban: 6 failures from another host → banned → refused; unban works; loopback/IAP never banned |
| `03-docker.sh [--apply]` | Docker's official apt repo (key fingerprint `9DC8 5822 9FC7 DD38 854A E2D8 8D81 803C 0EBF CD88` checked), Engine + Buildx + Compose plugins, enable at boot, `local` log driver (10 MB × 3), live-restore; stops if conflicting packages exist; keeps any existing `daemon.json` | Installed Engine 29.10.1, Compose v5.8.1, Buildx 0.39.1; enabled at boot; log driver `local`. The `hello-world` run could not be checked inside a container (nested overlayfs); the script verifies it on the VM |
| `04-prepare-webforge.sh` | Clones the branch into `/opt/webforge` (or fetches if present, never resets); checks no env file is tracked; checks `.env` safety values without printing secrets; lists required variables; checks resources; validates compose if `.env` exists | Fresh clone and re-run against a test origin |

Two defects were found by testing and fixed before release:
- **Fail2ban on Ubuntu 24.04 watched `sshd.service`**, but the unit is `ssh.service`, so it never saw a failed
  login. The jail now sets `journalmatch` for `ssh.service` and `mode = aggressive`, so key-only failures
  ("Connection closed by authenticating user … [preauth]") are counted.
- A failing `swapon` aborted the script and left `/swapfile` behind. It now cleans up and continues with a warning.

SSH-specific safety:
- The drop-in is `10-webforge-hardening.conf`. sshd keeps the first value it reads, so this file wins over the
  cloud-image defaults.
- SSH changes are skipped if the admin has no key or OS Login.
- The script runs `sshd -t` before reloading, and removes the file if the check fails.
- Existing sessions are not dropped.
- Undo: remove the file and `sudo systemctl reload ssh`.

## 3. Execution order on the VM (each step needs your approval)

Run everything from an SSH session to the VM, and keep that session open throughout.

```bash
curl -fsSL https://raw.githubusercontent.com/10-aqib/Auto-Master-/claude/gifted-meitner-ozj5y9/infrastructure/vps/01-inspect.sh -o ~/01-inspect.sh
```

```bash
less ~/01-inspect.sh
```

```bash
bash ~/01-inspect.sh | tee ~/webforge-inspect.txt
```

Review the output, then share it. It contains no secrets, but it does include the external IP. After approval:

```bash
sudo apt-get install -y git && git clone -q --branch claude/gifted-meitner-ozj5y9 --single-branch https://github.com/10-aqib/Auto-Master-.git ~/webforge-setup
```

```bash
sudo bash ~/webforge-setup/infrastructure/vps/02-harden.sh --swap 2G
```

```bash
sudo bash ~/webforge-setup/infrastructure/vps/02-harden.sh --apply --swap 2G
```

Now open a **second** SSH session and confirm you can log in before closing the first. Then:

```bash
sudo bash ~/webforge-setup/infrastructure/vps/03-docker.sh
```

```bash
sudo bash ~/webforge-setup/infrastructure/vps/03-docker.sh --apply
```

```bash
bash ~/webforge-setup/infrastructure/vps/04-prepare-webforge.sh
```

## 4. Resource compatibility (measured, not estimated)

Measured in the development sandbox while running the full 30-step end-to-end workflow (audits, renders,
validation, PDF, previews) at worker concurrency 1:

| Service | Idle | Peak (default limits) | Peak (small-VM limits) | Small-VM limit |
|---|---|---|---|---|
| browser (Chromium sandbox) | 36 MiB | 402 MiB | 343 MiB | 1024 MiB |
| api | 92 | 108 | 165 | 384 |
| worker | 84 | 88 | 88 | 384 |
| worker-audit | 84 | 104 | 103 | 320 |
| preview | 86 | 89 | 89 | 192 |
| dashboard | 42 | 121 | 89 | 320 |
| postgres | 47 | 73 | 69 | 384 |
| egress-proxy | 18 | 18 | 18 | 128 |
| redis | 4 | 5 | 5 | 128 |
| caddy + ops (production only) | not measured; ~120 expected | | | 128 + 192 |
| **Total** | **~0.5 GB** | **~1.0 GB** | **~0.97 GB** | |

Under the small-VM limits (`infrastructure/production/docker-compose.small-vm.yml`) the E2E run passed 30/30
with **no OOM kills and no restarts**. Real websites are heavier than the offline test fixtures, so Chromium
can use more memory; the 1 GB browser limit and 2 GB of swap leave headroom.

Disk: the images total about 5.9 GB (browser sandbox 4.33 GB, api 455 MB, dashboard 430 MB, postgres 434 MB,
redis 174 MB, caddy 92 MB). Building on the VM needs roughly 10 GB more for the build cache. Data and backups
are small at pilot scale (one full backup was about 4.2 MB).

Architecture: every pinned base image publishes linux/amd64 and linux/arm64, so E2 (x86-64) and T2A (ARM64) both work.

| VM shape | RAM | Verdict |
|---|---|---|
| e2-micro (free tier) | 1 GB | **Not viable.** Idle alone is ~0.5 GB, and Chromium plus image builds need more |
| e2-small | 2 GB | **Viable for the pilot** with 2 GB swap, the small-VM override, concurrency 1, and images built elsewhere or slowly with swap |
| e2-medium | 4 GB | Comfortable, but above the $15–20 budget (see §6) |
| Disk | — | **At least 30 GB** boot disk. The 10 GB default is not enough |

## 5. Security and deployment readiness

| Check | Status | Evidence / action |
|---|---|---|
| PostgreSQL not public | PASS (repository) | No host port in compose; smoke check "postgres port not published". On the VM: `ss -tlnp` in `01-inspect.sh` |
| Redis not public | PASS (repository) | Same, "redis port not published" |
| Only 80/443 published in production | PASS (repository) | `docker-compose.prod.yml`: Caddy only; dev ports bound to 127.0.0.1 |
| Docker bypasses UFW for published ports | Noted | Only Caddy publishes; the VPC firewall is the outer control |
| Secrets not in Git | PASS | `.env` ignored; no tracked env file (`04-prepare` checks); gitleaks in CI; the repository is **public**, so this matters |
| SSH restricted | Script ready | Keys only, no root, Fail2ban. Recommended (your action in the Cloud Console, free): limit the VPC rule for port 22 to the IAP range `35.235.240.0/20` and your own IP |
| HTTPS and domains | Documented, not done | Caddy obtains certificates automatically once three DNS names point at the VM: app, API and a **separate** preview origin. Needs domains and VPC rules for 80/443, both deployment-time actions |
| Off-site backups | Planned, not configured | `backup.sh` supports S3-compatible storage. Options (owner decision, may cost money): a Cloud Storage bucket with HMAC keys, or another S3-compatible provider. Keep `BACKUP_ENCRYPTION_KEY` offline too |
| Monitoring and alerting | Documented | Built-in `ops` service alerts every 5 min (set `ALERT_WEBHOOK_URL`); Compute Engine basic VM metrics; an external uptime check of `https://api.<domain>/health/live` (your choice) |
| Email | Locked | `EMAIL_SENDING_ENABLED=false`, `EMAIL_PROVIDER=mock`, `EMAIL_PAUSE=true` (checked by `04-prepare` once `.env` exists) |
| Google Places | Disabled | `GOOGLE_PLACES_API_ENABLED=false`; stays off until legal approval |
| Firebase | Untouched | No script reads or changes Firebase configuration; `01-inspect` only lists what runs on the VM |

## 6. Monthly cost considerations (approximate list prices; confirm in Google's pricing calculator)

| Item | Approx. per month | Notes |
|---|---|---|
| e2-small, on-demand, us-central1 | ~$12.2 | Third-party listings; prices differ by region |
| e2-medium, us-central1 | ~$24.5 | Over budget |
| External IPv4 in use | ~$3.65 | $0.005/hour since Feb 2024, ephemeral or static, while attached |
| 30 GB boot disk | ~$1.2 (standard) to ~$3 (balanced) | Approximate per-GB list prices; confirm |
| Network egress | low at pilot scale | Image pulls are inbound (free); outbound is previews and audits |
| **e2-small total** | **~$17–19** | Inside the $15–20 range, with little margin |

- An **ephemeral** IP changes if the VM is stopped and started, which would break DNS. A reserved static IP
  costs about the same while attached, but reserving one needs your approval; it is not done here.
- Unattached reserved IPs and leftover disks are billed. Any change of machine type or disk size needs your approval.
- Region matters: e2-micro free-tier regions (us-west1, us-central1, us-east1) don't help, because e2-micro is not viable.

## 7. Remaining deployment blockers (VM-specific additions to `docs/pilot/DEPLOYMENT_BLOCKERS.md`)

1. Phase 1 inspection output from the actual VM.
2. VM shape: at least e2-small with a 30 GB disk. If the VM is smaller, a resize needs your approval and costs more.
3. Image build strategy for a 2 GB VM: build on the VM with swap (slow; the 4.3 GB browser image pulls its base
   from Microsoft's registry), or build in CI and pull from a registry (needs a CI change).
4. Domains, DNS, and VPC firewall rules for 80/443 (deployment-time, your action).
5. Off-site backup destination and credentials.
6. CI result for the latest commit. The GitHub connector failed to connect in this session, so it was not checked.
7. Every item already listed in `docs/pilot/DEPLOYMENT_BLOCKERS.md` (legal review, email provider,
   penetration test, image re-scan).
