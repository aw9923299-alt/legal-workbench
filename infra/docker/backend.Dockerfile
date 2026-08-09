# syntax=docker/dockerfile:1

FROM ghcr.io/astral-sh/uv:0.12.3 AS uv

FROM python:3.12-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

WORKDIR /workspace/apps/backend

COPY --from=uv /uv /uvx /bin/
COPY apps/backend/pyproject.toml apps/backend/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project

COPY apps/backend ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable

FROM python:3.12-slim

ARG CODEX_CLI_VERSION

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/workspace/apps/backend/.venv/bin:${PATH}"

WORKDIR /workspace

RUN apt-get update \
    && apt-get install --no-install-recommends -y ca-certificates curl \
    && test -n "${CODEX_CLI_VERSION}" \
    && curl -fsSL \
        https://raw.githubusercontent.com/openai/codex/main/scripts/install/install.sh \
        -o /tmp/install-codex.sh \
    && CODEX_HOME=/opt/codex CODEX_INSTALL_DIR=/usr/local/bin CODEX_NON_INTERACTIVE=1 \
        sh /tmp/install-codex.sh --release "${CODEX_CLI_VERSION}" \
    && rm /tmp/install-codex.sh \
    && useradd --no-create-home --uid 10001 --shell /usr/sbin/nologin codex-agent \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /workspace/apps/backend/.venv /workspace/apps/backend/.venv
COPY --from=builder /workspace/apps/backend/alembic.ini /workspace/apps/backend/alembic.ini
COPY --from=builder /workspace/apps/backend/migrations /workspace/apps/backend/migrations
RUN chmod -R 0700 /workspace

CMD ["uvicorn", "legal_workbench.main:app", "--host", "0.0.0.0", "--port", "8000"]
