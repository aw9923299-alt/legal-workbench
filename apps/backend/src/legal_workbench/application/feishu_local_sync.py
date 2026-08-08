from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID, uuid4

from legal_workbench.application.message_analysis_policy import MessageAnalysisPolicy
from legal_workbench.application.ports import UnitOfWorkFactory
from legal_workbench.application.results import FeishuEventIngestedResult
from legal_workbench.domain.entities import IntegrationScope
from legal_workbench.domain.enums import (
    IntegrationIdentityType,
    IntegrationScopeStatus,
    IntegrationScopeType,
    IntegrationSyncMode,
)
from legal_workbench.domain.errors import DomainValidationError, EntityNotFoundError
from legal_workbench.integrations.feishu_local_connector import (
    LocalFeishuConnector,
    LocalFeishuRecord,
)


class LocalScopeService(Protocol):
    async def register_known_chat(
        self,
        *,
        chat_id: str,
        display_name: str | None,
        actor_id: str,
        actor_source: str,
        correlation_id: str,
        idempotency_key: str,
        identity_type: IntegrationIdentityType = IntegrationIdentityType.APP,
        scope_type: IntegrationScopeType = IntegrationScopeType.GROUP,
        authorization_id: UUID | None = None,
        backfill_days: int = 7,
    ) -> IntegrationScope: ...


class LocalIngestionAdapter(Protocol):
    async def ingest(
        self,
        *,
        record: LocalFeishuRecord,
        tenant_key: str,
        analysis_disposition: str,
        correlation_id: str,
    ) -> FeishuEventIngestedResult: ...


@dataclass(frozen=True, slots=True)
class LocalFeishuHostSyncResult:
    status: str
    records_discovered: int
    scopes_discovered: int
    ingested: int
    duplicates: int
    skipped: int
    generated_at: str
    source_channel: str
    discovery: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class LocalFeishuHostSyncService:
    """Mac-host composition for read-only local records into unified ingestion."""

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        *,
        connector: LocalFeishuConnector,
        scope_service: LocalScopeService,
        ingestion_adapter: LocalIngestionAdapter,
        analysis_policy: MessageAnalysisPolicy | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._connector = connector
        self._scope_service = scope_service
        self._ingestion_adapter = ingestion_adapter
        self._analysis_policy = analysis_policy or MessageAnalysisPolicy()

    async def sync(
        self,
        *,
        authorization_id: UUID,
        confirmed_account_hash: str | None,
    ) -> LocalFeishuHostSyncResult:
        report = self._connector.discover()
        discovered_records = self._connector.read_messages()
        discovery = self._redacted_discovery(report.to_dict())
        if not discovered_records:
            return self._result(
                status="supported_but_no_readable_local_records",
                records=0,
                scopes=0,
                ingested=0,
                duplicates=0,
                skipped=0,
                discovery=discovery,
            )
        normalized_hash = (confirmed_account_hash or "").strip().lower()
        if len(normalized_hash) != 64 or any(
            character not in "0123456789abcdef" for character in normalized_hash
        ):
            raise DomainValidationError("A valid confirmed local account hash is required.")
        records = tuple(
            record
            for record in discovered_records
            if hmac.compare_digest(
                hashlib.sha256(record.account_id.encode("utf-8")).hexdigest(),
                normalized_hash,
            )
        )
        if not records:
            raise DomainValidationError(
                "No readable records match the confirmed local account binding."
            )
        account_skipped = len(discovered_records) - len(records)

        async with self._uow_factory() as uow:
            authorization = await uow.feishu_user_authorizations.get_authorization(
                authorization_id
            )
        if authorization is None:
            raise EntityNotFoundError("Feishu user authorization was not found.")

        scopes: dict[tuple[str, IntegrationScopeType], IntegrationScope] = {}
        for record in records:
            scope_type = self._scope_type(record)
            if scope_type is None:
                continue
            key = (record.chat_id, scope_type)
            if key in scopes:
                continue
            scopes[key] = await self._scope_service.register_known_chat(
                chat_id=record.chat_id,
                display_name=None,
                actor_id="feishu-local-connector",
                actor_source="feishu-local-discovery",
                correlation_id=f"feishu-local-discovery:{authorization_id}",
                idempotency_key=(
                    f"local-discover:{authorization_id}:{scope_type.value}:"
                    f"{record.chat_id}"
                ),
                identity_type=IntegrationIdentityType.USER,
                scope_type=scope_type,
                authorization_id=authorization_id,
            )

        ingested = 0
        duplicates = 0
        skipped = account_skipped
        correlation_id = f"feishu-local-host:{uuid4()}"
        for record in records:
            scope_type = self._scope_type(record)
            scope = scopes.get((record.chat_id, scope_type)) if scope_type else None
            if scope is None:
                skipped += 1
                continue
            disposition = "store_only"
            if (
                scope.status == IntegrationScopeStatus.ALLOWED
                and scope.sync_mode != IntegrationSyncMode.DISABLED
            ):
                disposition = self._analysis_policy.decide(
                    raw_message=self._policy_message(record),
                    scope=scope,
                    self_open_id=authorization.open_id,
                ).disposition
            result = await self._ingestion_adapter.ingest(
                record=record,
                tenant_key=authorization.tenant_key,
                analysis_disposition=disposition,
                correlation_id=correlation_id,
            )
            ingested += 1
            duplicates += int(bool(getattr(result, "duplicate", False)))

        return self._result(
            status="partial" if skipped else "completed",
            records=len(records),
            scopes=len(scopes),
            ingested=ingested,
            duplicates=duplicates,
            skipped=skipped,
            discovery=discovery,
        )

    @staticmethod
    def _redacted_discovery(discovery: dict[str, object]) -> dict[str, object]:
        allowed = (
            "client_installed",
            "roots_checked",
            "roots_readable",
            "database_files",
            "readable_message_databases",
            "readable_attachment_indexes",
            "opaque_or_encrypted_databases",
            "credential_locations_excluded",
            "read_only",
        )
        return {
            key: discovery[key]
            for key in allowed
            if key in discovery
        }

    @staticmethod
    def _scope_type(record: LocalFeishuRecord) -> IntegrationScopeType | None:
        normalized = record.chat_type.strip().lower()
        if normalized == "p2p":
            return IntegrationScopeType.P2P
        if normalized == "group":
            return IntegrationScopeType.GROUP
        return None

    @staticmethod
    def _policy_message(record: LocalFeishuRecord) -> dict[str, object]:
        return {
            "content": record.content,
            "body": {
                "content": json.dumps(record.content, ensure_ascii=False),
            },
            "sender_id": record.sender_id or "",
            "message_type": record.message_type,
        }

    @staticmethod
    def _result(
        *,
        status: str,
        records: int,
        scopes: int,
        ingested: int,
        duplicates: int,
        skipped: int,
        discovery: dict[str, object],
    ) -> LocalFeishuHostSyncResult:
        return LocalFeishuHostSyncResult(
            status=status,
            records_discovered=records,
            scopes_discovered=scopes,
            ingested=ingested,
            duplicates=duplicates,
            skipped=skipped,
            generated_at=datetime.now(UTC).isoformat(),
            source_channel="local_client",
            discovery=discovery,
        )
