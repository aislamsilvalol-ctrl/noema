.PHONY: help up down check fmt lint types test test-api test-web e2e migrate clean

help:
	@grep -E '^[a-z-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

up:  ## Start the full stack
	docker compose up --build

down:  ## Stop the stack
	docker compose down

check: lint types test  ## Everything CI runs

fmt:  ## Format
	cd apps/api && uv run ruff format . && uv run ruff check --fix .
	cd apps/web && pnpm format

lint:
	cd apps/api && uv run ruff check . && uv run ruff format --check .
	cd apps/web && pnpm lint

types:
	cd apps/api && uv run mypy .
	cd apps/web && pnpm typecheck

test: test-api test-web

test-api:
	cd apps/api && uv run pytest --cov=noema --cov-report=term-missing

test-web:
	cd apps/web && pnpm test

e2e:  ## Playwright against a running stack
	cd e2e && npx playwright test

migrate:  ## Apply migrations
	cd apps/api && uv run alembic upgrade head

revision:  ## make revision m="add concept edges"
	cd apps/api && uv run alembic revision --autogenerate -m "$(m)"

clean:
	docker compose down -v
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	rm -rf apps/api/.pytest_cache apps/api/.mypy_cache apps/web/.next
