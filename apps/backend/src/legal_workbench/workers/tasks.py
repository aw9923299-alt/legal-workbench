import asyncio
from typing import Any
from uuid import UUID

from legal_workbench.infrastructure.celery_app import celery_app
from legal_workbench.infrastructure.outbox import OutboxDispatcher, mark_feishu_message_queued


@celery_app.task(name="system.ping")
def ping(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"status": "ok", "payload": payload or {}}


@celery_app.task(name="outbox.publish")
def publish_outbox() -> dict[str, int]:
    count = asyncio.run(OutboxDispatcher().publish_batch())
    return {"claimed": count}


@celery_app.task(name="feishu.process_message")
def process_feishu_message(message_id: str) -> dict[str, str]:
    asyncio.run(mark_feishu_message_queued(UUID(message_id)))
    return {"messageId": message_id, "status": "queued_for_analysis"}
