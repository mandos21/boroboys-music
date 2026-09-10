.DEFAULT_GOAL := help

POETRY_VERSION ?= 2.1.1
POETRY ?= $(shell command -v poetry 2>/dev/null || printf '%s/.local/bin/poetry' "$(HOME)")

.PHONY: help setup dev-setup bootstrap db-up db-down test-db migrate task-schema api worker web api-contract test e2e visual a11y lint typecheck verify history-dry-run history-import history-artwork history-genres docker-env docker-build docker-up docker-down docker-logs

TEST_DATABASE_URL ?= postgresql+psycopg://music_rounds:music_rounds@localhost:5432/music_rounds_test

help: ## Show commands
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "%-16s %s\n", $$1, $$2}'

setup: ## Install Poetry, backend, and frontend development dependencies
	@command -v python3 >/dev/null || (echo "python3 is required" >&2; exit 1)
	@if ! command -v poetry >/dev/null && [ ! -x "$(POETRY)" ] && ! command -v curl >/dev/null; then echo "curl is required to install Poetry automatically" >&2; exit 1; fi
	@if ! command -v poetry >/dev/null && [ ! -x "$(POETRY)" ]; then \
		echo "Poetry not found; installing Poetry $(POETRY_VERSION)"; \
		curl -sSL https://install.python-poetry.org | python3 - --version "$(POETRY_VERSION)"; \
	fi
	@test -x "$(POETRY)" || (echo "Poetry is unavailable at $(POETRY); add it to PATH or set POETRY=/path/to/poetry" >&2; exit 1)
	@command -v npm >/dev/null || (echo "npm is required for local frontend development; use Docker targets if Node.js is unavailable" >&2; exit 1)
	@if [ ! -f .env ]; then cp .env.example .env; echo "Created .env from .env.example; review local secrets before starting"; fi
	cd backend && "$(POETRY)" install --with dev
	cd frontend && npm ci

dev-setup: setup ## Alias for setup

bootstrap: setup ## Backwards-compatible alias for setup

db-up: ## Start PostgreSQL
	docker compose up -d postgres

db-down: ## Stop PostgreSQL
	docker compose down

test-db: db-up ## Create the isolated PostgreSQL database used by tests
	@docker compose exec -T postgres sh -c 'psql -U music_rounds -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname = '\''music_rounds_test'\''" | grep -q 1 || createdb -U music_rounds music_rounds_test'

migrate: ## Apply Alembic migrations
	cd backend && "$(POETRY)" run alembic upgrade head

task-schema: migrate ## Apply/check Procrastinate schema through Alembic
	@echo "Procrastinate schema is managed by Alembic migrations."

api: db-up migrate ## Start PostgreSQL, apply migrations, then run FastAPI
	cd backend && "$(POETRY)" run uvicorn app.main:app --reload --port 8000

worker: ## Run Procrastinate worker
	cd backend && "$(POETRY)" run procrastinate --app=app.tasks.app worker

web: ## Run Vite
	cd frontend && npm run dev

api-contract: ## Regenerate OpenAPI JSON and frontend API types
	cd backend && "$(POETRY)" run python scripts/generate_openapi.py > openapi.json
	cd frontend && npm run generate:api

test: test-db ## Run tests against the isolated test database
	cd backend && DATABASE_URL="$(TEST_DATABASE_URL)" "$(POETRY)" run alembic upgrade head
	cd backend && TEST_DATABASE_URL="$(TEST_DATABASE_URL)" "$(POETRY)" run pytest
	cd frontend && npm run test -- --run

e2e: ## Run deterministic browser integration and visual-regression coverage
	cd frontend && npm run test:e2e

visual: ## Run screenshot comparisons across supported viewport and theme combinations
	cd frontend && npm run test:visual

a11y: ## Run accessibility smoke checks against representative application pages
	cd frontend && npm run test:a11y

lint: ## Run linters
	cd backend && "$(POETRY)" run ruff check . && "$(POETRY)" run ruff format --check app tests
	cd frontend && npm run lint && npm run format:check

typecheck: ## Run type checks
	cd backend && "$(POETRY)" run mypy app
	cd frontend && npm run typecheck

verify: test-db ## Run the local release-quality gate against the isolated test database
	cd backend && DATABASE_URL="$(TEST_DATABASE_URL)" "$(POETRY)" run alembic upgrade head && DATABASE_URL="$(TEST_DATABASE_URL)" "$(POETRY)" run alembic check && "$(POETRY)" run ruff check . && "$(POETRY)" run ruff format --check app tests && "$(POETRY)" run mypy app && TEST_DATABASE_URL="$(TEST_DATABASE_URL)" "$(POETRY)" run pytest
	cd frontend && npm run lint && npm run format:check && npm run typecheck && npm run build

history-dry-run: ## Validate a private history bundle (requires SERIES_SLUG, PUBLISHER_ACCOUNT_ID, IDENTITY_MAP)
	@test -n "$(SERIES_SLUG)" || (echo "SERIES_SLUG is required" >&2; exit 2)
	@test -n "$(PUBLISHER_ACCOUNT_ID)" || (echo "PUBLISHER_ACCOUNT_ID is required" >&2; exit 2)
	@test -n "$(IDENTITY_MAP)" || (echo "IDENTITY_MAP is required" >&2; exit 2)
	cd backend && "$(POETRY)" run python -m app.cli.import_historical_playlists --series-slug "$(SERIES_SLUG)" --publisher-account-id "$(PUBLISHER_ACCOUNT_ID)" --playlist-dir ../playlist_rounds --identity-map "$(IDENTITY_MAP)" --dry-run

history-import: ## Import private history (also set CONFIRM_HISTORICAL_IMPORT=yes)
	@test "$(CONFIRM_HISTORICAL_IMPORT)" = "yes" || (echo "Set CONFIRM_HISTORICAL_IMPORT=yes after reviewing history-dry-run" >&2; exit 2)
	@test -n "$(SERIES_SLUG)" || (echo "SERIES_SLUG is required" >&2; exit 2)
	@test -n "$(PUBLISHER_ACCOUNT_ID)" || (echo "PUBLISHER_ACCOUNT_ID is required" >&2; exit 2)
	@test -n "$(IDENTITY_MAP)" || (echo "IDENTITY_MAP is required" >&2; exit 2)
	cd backend && "$(POETRY)" run python -m app.cli.import_historical_playlists --series-slug "$(SERIES_SLUG)" --publisher-account-id "$(PUBLISHER_ACCOUNT_ID)" --playlist-dir ../playlist_rounds --identity-map "$(IDENTITY_MAP)"

history-artwork: ## Cache album art using configured Spotify app credentials
	cd backend && "$(POETRY)" run python -m app.cli.backfill_track_artwork --client-credentials

history-genres: ## Backfill canonical Spotify artists and cached genres for historical tracks
	cd backend && "$(POETRY)" run python -m app.cli.backfill_historical_track_metadata

docker-env: ## Create a local Docker environment file if needed
	@if [ ! -f .env ]; then cp .env.example .env; echo "Created .env from .env.example; review local secrets before starting"; fi

docker-build: docker-env ## Build the API, worker, and frontend images
	docker compose build

docker-up: docker-env ## Build and start the complete local Docker stack
	docker compose up -d --build

docker-down: docker-env ## Stop the complete local Docker stack
	docker compose down

docker-logs: docker-env ## Follow API, worker, and frontend container logs
	docker compose logs -f api worker web
