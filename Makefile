# WEBFORGE AI developer commands. Run `make help`.
SHELL := /usr/bin/env bash
.DEFAULT_GOAL := help

API_DIR := apps/api
DASH_DIR := apps/dashboard
UV := uv --directory $(API_DIR)
NPM := npm --prefix $(DASH_DIR)

TEST_DB_URL := postgresql://webforge:webforge-test-only@127.0.0.1:55432/webforge
TEST_REDIS_URL := redis://127.0.0.1:56379/0
TEST_COMPOSE := docker compose -f infrastructure/docker/compose.test.yml

.PHONY: help env install dev up down logs ps smoke lint format typecheck test test-integration test-services-up test-services-down build compose-config migrate owner contracts e2e clean

help: ## Show available commands
	@grep -E '^[a-zA-Z0-9_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS=":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

env: ## Create .env with fresh random secrets (never overwrites)
	@python3 infrastructure/scripts/generate-env.py || true

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

test: ## Fast tests (database tests are skipped without TEST_DATABASE_URL)
	$(UV) run pytest
	$(NPM) test

test-services-up: ## Start throwaway Postgres/Redis for integration tests
	$(TEST_COMPOSE) up -d --wait

test-services-down: ## Stop the throwaway test services
	$(TEST_COMPOSE) down -v

test-integration: test-services-up ## Full API suite against real Postgres/Redis, then dashboard tests
	TEST_DATABASE_URL=$(TEST_DB_URL) TEST_REDIS_URL=$(TEST_REDIS_URL) REQUIRE_DB_TESTS=1 $(UV) run pytest
	$(NPM) test

contracts: ## Regenerate packages/contracts/openapi.json from the API code
	$(UV) run python -m webforge_api.cli openapi > packages/contracts/openapi.json

e2e: ## Browser end-to-end auth test against `make dev` (needs an empty users table)
	npm --prefix tests/e2e ci --no-audit --no-fund
	node tests/e2e/auth-flow.mjs

migrate: ## Apply database migrations in the running stack
	docker compose run --rm migrate

owner: ## One-time owner bootstrap: make owner EMAIL=you@domain NAME="Your Name"
	@test -n "$(EMAIL)" -a -n "$(NAME)" || (echo 'Usage: make owner EMAIL=you@domain NAME="Your Name"' && exit 1)
	docker compose exec api python -m webforge_api.cli bootstrap-owner --email "$(EMAIL)" --name "$(NAME)"

build: ## Production builds (dashboard bundle + container images)
	$(NPM) run build
	docker compose build

compose-config: ## Validate docker-compose.yml against .env
	docker compose config --quiet && echo "compose config OK"

clean: ## Remove local build/test caches (keeps .env and Docker volumes)
	rm -rf $(API_DIR)/.pytest_cache $(API_DIR)/.mypy_cache $(API_DIR)/.ruff_cache
	rm -rf $(DASH_DIR)/.next $(DASH_DIR)/coverage
	find $(API_DIR) -name __pycache__ -type d -prune -exec rm -rf {} +
