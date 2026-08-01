.PHONY: setup-web setup-backend web-dev backend-dev test lint compose-up compose-down compose-logs migrate

PYTHON := .venv/bin/python

setup-web:
	npm install

setup-backend:
	python3 -m venv .venv
	$(PYTHON) -m pip install -e 'apps/backend[dev]'

web-dev:
	npm run dev

backend-dev:
	$(PYTHON) -m uvicorn legal_workbench.main:app --app-dir apps/backend/src --reload --port 8000

test:
	$(PYTHON) -m pytest apps/backend/tests

lint:
	$(PYTHON) -m ruff check apps/backend/src apps/backend/tests
	$(PYTHON) -m mypy --config-file apps/backend/pyproject.toml apps/backend/src
	npm run typecheck

migrate:
	$(PYTHON) -m alembic -c apps/backend/alembic.ini upgrade head

compose-up:
	docker compose up -d --build

compose-down:
	docker compose down

compose-logs:
	docker compose logs -f
