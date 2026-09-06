.DEFAULT_GOAL := help

.PHONY: help bootstrap db-up db-down migrate task-schema api worker web test lint typecheck verify

help: ## Show commands
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "%-16s %s\n", $$1, $$2}'

bootstrap: ## Install dependencies
	cd backend && poetry install
	cd frontend && npm install

db-up: ## Start PostgreSQL
	docker compose up -d postgres

db-down: ## Stop PostgreSQL
	docker compose down

migrate: ## Apply Alembic migrations
	cd backend && poetry run alembic upgrade head

task-schema: ## Apply/check Procrastinate schema
	cd backend && poetry run procrastinate --app=app.tasks.app schema --apply

api: ## Run FastAPI
	cd backend && poetry run uvicorn app.main:app --reload --port 8000

worker: ## Run Procrastinate worker
	cd backend && poetry run procrastinate --app=app.tasks.app worker

web: ## Run Vite
	cd frontend && npm run dev

test: ## Run tests
	cd backend && poetry run pytest
	cd frontend && npm run test -- --run

lint: ## Run linters
	cd backend && poetry run ruff check .
	cd frontend && npm run lint

typecheck: ## Run type checks
	cd backend && poetry run mypy app
	cd frontend && npm run typecheck

verify: ## Run the local release-quality gate (PostgreSQL must be running)
	cd backend && poetry run alembic upgrade head && poetry run alembic check && poetry run ruff check . && poetry run mypy app && poetry run pytest
	cd frontend && npm run lint && npm run typecheck && npm run build
