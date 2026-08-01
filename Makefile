.PHONY: setup-web setup-backend web-dev backend-dev test lint compose-up compose-down compose-logs migrate

setup-web:
	npm install

setup-backend:
	python -m pip install -e 'apps/backend[dev]'

web-dev:
	npm run dev

backend-dev:
	python -m uvicorn legal_workbench.main:app --app-dir apps/backend/src --reload --port 8000

test:
	python -m pytest apps/backend/tests

lint:
	python -m ruff check apps/backend/src apps/backend/tests
	python -m mypy --config-file apps/backend/pyproject.toml apps/backend/src
	npm run typecheck

migrate:
	alembic -c apps/backend/alembic.ini upgrade head

compose-up:
	docker compose up -d --build

compose-down:
	docker compose down

compose-logs:
	docker compose logs -f
