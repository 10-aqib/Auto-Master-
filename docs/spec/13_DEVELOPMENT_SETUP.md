# 13 — Development Setup (Windows + WSL Recommended)

Commands are a starting point. Official installer/package instructions can change; use official sources and record actual versions. Never paste keys into terminal history/chat.

## 1. Windows prerequisites

1. Windows 10/11 with virtualization enabled.
2. Open PowerShell as Administrator and install WSL2 + Ubuntu 24.04:

```powershell
wsl --install -d Ubuntu-24.04
```

3. Restart if requested; launch Ubuntu from Start menu.
4. Keep repository inside WSL filesystem, e.g. `~/projects/webforge-ai`, for better Docker/file performance where possible.

## 2. Update Ubuntu and install base tools

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y git curl wget unzip build-essential ca-certificates gnupg lsb-release python3 python3-venv python3-pip python3-dev
```

Install Docker Engine and Compose plugin using current official instructions: https://docs.docker.com/engine/install/ubuntu/ . Prefer the official Docker repository. Follow post-install guidance carefully; Docker group membership grants powerful host privileges.

## 3. Node.js

Use a maintained Node version manager and current supported LTS. Example with nvm:

```bash
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/master/install.sh | bash
source ~/.bashrc
nvm install --lts
nvm use --lts
node --version
npm --version
```

If installer instructions change, follow official nvm documentation.

## 4. Claude Code

Install using Anthropic's current official guide: https://code.claude.com/docs/en/overview . Example Linux installer command documented by Anthropic:

```bash
curl -fsSL https://claude.ai/install.sh | bash
```

Then run `claude`, authenticate using supported flow and verify `claude --version`. Claude Code authentication and production Anthropic API billing are distinct concerns; verify what credentials the production app will use. Never put provider keys in frontend files.

## 5. Create/open project

```bash
mkdir -p ~/projects/webforge-ai
cd ~/projects/webforge-ai
# Extract this ZIP here, or copy its contents into this directory.
git init
```

Confirm `CLAUDE.md` is at repository root. Start Claude Code from this folder so it reads project guidance.

## 6. Local configuration

```bash
cp .env.example .env
chmod 600 .env
```

Leave real integration keys blank until the relevant phase. Never commit `.env`.

## 7. Optional tools

VS Code with WSL extension; private GitHub repo with SSH auth; Docker Desktop WSL integration or Docker Engine inside WSL (choose one coherent setup); password manager for API keys/recovery codes.

## 8. Start Phase 00

```bash
claude
```

Paste `PHASE_PROMPTS/PHASE_00_FOUNDATION.md`. Require Claude to inspect the handoff and implement Phase 00 only.

## 9. Expected development commands

Claude should create/document a consistent command set, e.g.:

```bash
make help
make dev
make lint
make typecheck
make test
make test-integration
make build
make migrate
make down
```

These commands do not exist until Phase 00 creates them. Check the actual Makefile/package scripts before using them.

## 10. Common issues

- Docker unavailable in WSL: verify Docker Engine/Desktop integration and WSL status.
- `claude` not found: reopen shell, source profile and check official install/troubleshooting docs.
- Runtime version mismatch: follow pinned version files and use version managers.
- Playwright browser missing: install browser/runtime dependencies in worker image using current Playwright instructions.
- Port in use: identify the process before stopping anything.
- Git auth issue: use SSH or official credential manager; never embed a token in remote URL.
