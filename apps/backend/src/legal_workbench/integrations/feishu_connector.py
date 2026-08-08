from __future__ import annotations

import asyncio
import signal
from contextlib import suppress

import structlog

from legal_workbench.application.commands import IngestFeishuEventCommand
from legal_workbench.application.feishu_handlers import IngestFeishuEventHandler
from legal_workbench.application.feishu_operations import FeishuOperationsService
from legal_workbench.config import FeishuEventSourceMode, get_settings
from legal_workbench.infrastructure.feishu_personal_runtime import (
    PersonalSyncRuntimeFactory,
)
from legal_workbench.infrastructure.unit_of_work import SqlAlchemyUnitOfWorkFactory
from legal_workbench.integrations.feishu_event_sources import (
    EventSourceHealth,
    EventSourceStatus,
    LongConnectionFeishuEventSource,
)
from legal_workbench.integrations.feishu_sdk import OfficialFeishuSdkConnection

logger = structlog.get_logger(__name__)


def _required_object(value: object, name: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"Feishu event {name} must be an object")
    return {str(key): child for key, child in value.items()}


async def run_connector() -> None:
    settings = get_settings()
    uow_factory = SqlAlchemyUnitOfWorkFactory()
    operations = FeishuOperationsService(settings=settings, uow_factory=uow_factory)
    stop_requested = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop_requested.set)

    if not settings.enable_real_feishu:
        await operations.persist_health(EventSourceHealth(status=EventSourceStatus.DISABLED))
        logger.warning("feishu_connector_disabled", reason="ENABLE_REAL_FEISHU is false")
        await stop_requested.wait()
        return
    if settings.feishu_event_source != FeishuEventSourceMode.LONG_CONNECTION:
        await operations.persist_health(EventSourceHealth(status=EventSourceStatus.DISABLED))
        logger.info("feishu_connector_webhook_mode", reason="API callback owns event intake")
        await stop_requested.wait()
        return

    app_id, app_secret = await PersonalSyncRuntimeFactory(
        settings=settings,
        uow_factory=uow_factory,
    ).resolve_app_credentials()

    source: LongConnectionFeishuEventSource

    async def ingest(payload: dict[str, object]) -> None:
        header = _required_object(payload.get("header"), "header")
        event_id = str(header.get("event_id") or "").strip()
        event_type = str(header.get("event_type") or "").strip()
        if not event_id or not event_type:
            raise ValueError("Feishu event_id and event_type are required")
        result = await IngestFeishuEventHandler(uow_factory).execute(
            IngestFeishuEventCommand(
                actor_id="feishu-long-connection",
                correlation_id=f"feishu:{event_id}",
                event_id=event_id,
                event_type=event_type,
                tenant_key=str(header.get("tenant_key") or "") or None,
                app_id=str(header.get("app_id") or "") or None,
                schema_version=str(payload.get("schema") or "") or None,
                raw_payload=payload,
            )
        )
        await source.record_event()
        if result.message_id is not None:
            await operations.download_attachments(result.message_id)

    sdk = OfficialFeishuSdkConnection(
        app_id=app_id,
        app_secret=app_secret,
        encrypt_key=settings.feishu_encrypt_key,
        verification_token=settings.feishu_verification_token,
        sink=ingest,
        on_reconnecting=lambda: source.record_reconnecting(),
        on_reconnected=lambda: source.record_reconnected(),
    )

    async def persist_health(health: EventSourceHealth) -> None:
        await operations.persist_health(health)

    source = LongConnectionFeishuEventSource(
        connect=sdk.connect,
        disconnect=sdk.disconnect,
        state_changed=persist_health,
        maximum_backoff_seconds=settings.feishu_reconnect_max_seconds,
    )

    async def monitor_manual_reconnect() -> None:
        while not stop_requested.is_set():
            await asyncio.sleep(2)
            connection = await operations.get_connection()
            if connection.last_error_code != "MANUAL_RECONNECT_REQUESTED":
                continue
            logger.info("feishu_manual_reconnect_started")
            await source.stop()
            await source.start()

    await source.start()
    monitor = asyncio.create_task(monitor_manual_reconnect(), name="feishu-reconnect-monitor")
    try:
        await stop_requested.wait()
    finally:
        monitor.cancel()
        with suppress(asyncio.CancelledError):
            await monitor
        await source.stop()


def main() -> None:
    try:
        asyncio.run(run_connector())
    except Exception as exc:
        logger.critical(
            "feishu_connector_failed_closed",
            error_code=type(exc).__name__,
            error_message=str(exc)[:1000],
        )
        raise


if __name__ == "__main__":
    main()
