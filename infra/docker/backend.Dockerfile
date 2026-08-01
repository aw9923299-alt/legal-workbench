FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /workspace

COPY apps/backend /workspace/apps/backend
RUN python -m pip install --no-cache-dir /workspace/apps/backend

ENV PYTHONPATH=/workspace/apps/backend/src
CMD ["uvicorn", "legal_workbench.main:app", "--host", "0.0.0.0", "--port", "8000"]
