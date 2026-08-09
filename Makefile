.PHONY: setup setup-web setup-backend web-dev backend-dev test lint migrate feishu-local-sync knowledge-import compose compose-up compose-down compose-logs ops-start ops-stop ops-wake-check ops-backup ops-diagnostics ops-cleanup

BACKEND_DIR := apps/backend
BACKEND_UV := cd $(BACKEND_DIR) && uv run --locked

setup: setup-web setup-backend

setup-web:
	npm ci --no-audit --no-fund

setup-backend:
	cd $(BACKEND_DIR) && uv sync --locked

web-dev:
	npm run dev

backend-dev:
	$(BACKEND_UV) uvicorn legal_workbench.main:app --reload --host 127.0.0.1 --port 8000

test:
	$(BACKEND_UV) pytest
	npm run test

lint:
	$(BACKEND_UV) ruff check src tests
	$(BACKEND_UV) mypy --config-file pyproject.toml src
	npm run typecheck

migrate:
	$(BACKEND_UV) alembic -c alembic.ini upgrade head

feishu-local-sync:
	$(BACKEND_UV) python -m legal_workbench.integrations.feishu_local_connector --sync --authorization-id "$(AUTHORIZATION_ID)" --account-id-hash "$(ACCOUNT_ID_HASH)"

knowledge-import:
	@test -n "$(SOURCE)" || (echo 'SOURCE is required' >&2; exit 2)
	$(BACKEND_UV) python -m legal_workbench.integrations.local_knowledge_importer --source "$(SOURCE)" --source-root-key "$(or $(SOURCE_ROOT_KEY),codex_obs_legal)"

compose: compose-up

compose-up:
	docker compose up -d --build

compose-down:
	docker compose down

compose-logs:
	docker compose logs -f

ops-start:
	$(BACKEND_UV) python ../../scripts/legal_workbench_ops.py start

ops-stop:
	$(BACKEND_UV) python ../../scripts/legal_workbench_ops.py stop

ops-wake-check:
	$(BACKEND_UV) python ../../scripts/legal_workbench_ops.py wake-check

ops-backup:
	$(BACKEND_UV) python ../../scripts/legal_workbench_ops.py backup

ops-diagnostics:
	$(BACKEND_UV) python ../../scripts/legal_workbench_ops.py diagnostics

ops-cleanup:
	$(BACKEND_UV) python ../../scripts/legal_workbench_ops.py cleanup
