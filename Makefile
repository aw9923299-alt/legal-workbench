.PHONY: setup-web setup-backend web-dev backend-dev test lint compose-up compose-down compose-logs migrate feishu-local-sync ops-start ops-stop ops-wake-check ops-backup ops-diagnostics ops-cleanup

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

feishu-local-sync:
	PYTHONPATH=apps/backend/src $(PYTHON) -m legal_workbench.integrations.feishu_local_connector --sync --authorization-id "$(AUTHORIZATION_ID)" --account-id-hash "$(ACCOUNT_ID_HASH)"

compose-up:
	docker compose up -d --build

compose-down:
	docker compose down

compose-logs:
	docker compose logs -f

ops-start:
	$(PYTHON) scripts/legal_workbench_ops.py start

ops-stop:
	$(PYTHON) scripts/legal_workbench_ops.py stop

ops-wake-check:
	$(PYTHON) scripts/legal_workbench_ops.py wake-check

ops-backup:
	$(PYTHON) scripts/legal_workbench_ops.py backup

ops-diagnostics:
	$(PYTHON) scripts/legal_workbench_ops.py diagnostics

ops-cleanup:
	$(PYTHON) scripts/legal_workbench_ops.py cleanup
