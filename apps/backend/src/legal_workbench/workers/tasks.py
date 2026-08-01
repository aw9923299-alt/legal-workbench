from typing import Any

from legal_workbench.infrastructure.celery_app import celery_app


@celery_app.task(name="system.ping")
def ping(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Minimal task used to validate the queue and worker lifecycle."""

    return {"status": "ok", "payload": payload or {}}
