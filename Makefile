# WEBFORGE AI developer commands. Run `make help`.
SHELL := /usr/bin/env bash
.DEFAULT_GOAL := help

API_DIR := apps/api
DASH_DIR := apps/dashboard
UV := uv --directory $(API_DIR)
NPM := npm --prefix $(DASH_DIR)

.PHONY: help env install dev up down logs ps smoke lint format typecheck test build compose-config clean

help: ## Show available commands
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS=":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

env: ## Create a local .env from .env.example (never overwrites)
	@if [ -f .env ]; then echo ".env already exists"; else cp .env.example .env && chmod 600 .env && echo "Created .env. Replace every CHANGE_ME value before running 'make dev'."; fi

install: ## Install API and dashboard dependencies from lockfiles
	$(UV) sync --frozen
	$(NPM) ci --no-audit --no-fund

dev: ## Build and start the local Docker stack (waits for healthchecks)
	@test -f .env || (echo "Missing .env. Run 'make env' first." && exit 1)
	docker compose up -d --build --wait

up: dev ## Alias for dev

down: ## Stop the local stack (keeps volumes)
	docker compose down

logs: ## Follow logs from all services
	docker compose logs -f --tail=100

ps: ## Show service status
	docker compose ps

smoke: ## Smoke-test the running stack (health, readiness, ports)
	infrastructure/scripts/smoke.sh

lint: ## Lint and format-check API and dashboard
	$(UV) run ruff format --check .
	$(UV) run ruff check .
	$(NPM) run lint
	$(NPM) run format:check

format: ## Auto-format API and dashboard
	$(UV) run ruff format .
	$(UV) run ruff check --fix .
	$(NPM) run format

typecheck: ## Static type checks (mypy strict, tsc strict)
	$(UV) run mypy
	$(NPM) run typecheck

test: ## Unit tests (API pytest, dashboard vitest)
	$(UV) run pytest
	$(NPM) test

build: ## Production builds (dashboard bundle + container images)
	$(NPM) run build
	docker compose build

compose-config: ## Validate docker-compose.yml against .env
	docker compose config --quiet && echo "compose config OK"

clean: ## Remove local build/test caches (keeps .env and Docker volumes)
	rm -rf $(API_DIR)/.pytest_cache $(API_DIR)/.mypy_cache $(API_DIR)/.ruff_cache
	rm -rf $(DASH_DIR)/.next $(DASH_DIR)/coverage
	find $(API_DIR) -name __pycache__ -type d -prune -exec rm -rf {} +
