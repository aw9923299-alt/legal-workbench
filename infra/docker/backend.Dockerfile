FROM python:3.12-slim

ARG CODEX_CLI_VERSION

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

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

COPY apps/backend /workspace/apps/backend
RUN python -m pip install --no-cache-dir /workspace/apps/backend
RUN chmod -R 0700 /workspace

ENV PYTHONPATH=/workspace/apps/backend/src
CMD ["uvicorn", "legal_workbench.main:app", "--host", "0.0.0.0", "--port", "8000"]
