import asyncio
import json
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from legal_workbench.api.routes.system import collect_system_health
from legal_workbench.config import Settings, get_settings

router = APIRouter(prefix="/events", tags=["events"])


@router.get("/stream")
async def event_stream(
    settings: Annotated[Settings, Depends(get_settings)],
) -> StreamingResponse:
    async def events() -> AsyncIterator[str]:
        sequence = 0
        previous_metrics: dict[str, object] | None = None
        while True:
            sequence += 1
            try:
                payload = await collect_system_health(settings)
                data = json.dumps(
                    payload.model_dump(by_alias=True, mode="json"),
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                yield f"id: {sequence}\nevent: system.health\ndata: {data}\n\n"
                metrics = (
                    payload.metrics.model_dump(by_alias=True, mode="json")
                    if payload.metrics
                    else None
                )
                if metrics is not None and previous_metrics is not None:
                    change_events = {
                        "message.ingested": ("lastMessageAt",),
                        "agent-run.updated": (
                            "lastAgentRunUpdateAt",
                            "agentQueued",
                            "failedRuns",
                            "agentDeadLetters",
                        ),
                        "candidate.created": ("lastCandidateAt",),
                        "outbox.failed": (
                            "lastOutboxFailureAt",
                            "outboxDeadLetters",
                        ),
                    }
                    for event_name, keys in change_events.items():
                        if any(metrics.get(key) != previous_metrics.get(key) for key in keys):
                            sequence += 1
                            yield f"id: {sequence}\nevent: {event_name}\ndata: {data}\n\n"
                previous_metrics = metrics
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                error = json.dumps(
                    {"code": "SSE_SNAPSHOT_FAILED", "detail": type(exc).__name__}
                )
                yield f"event: error\ndata: {error}\n\n"
            await asyncio.sleep(5)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
