from __future__ import annotations

import argparse
import asyncio
import json
from collections.abc import Awaitable
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import UUID

import httpx
from pydantic import BaseModel, ConfigDict

from legal_workbench.application.feishu_capabilities import (
    CAPABILITY_LABELS,
    FeishuCapability,
    project_capabilities,
)
from legal_workbench.application.feishu_user_auth import FeishuUserTokenProvider
from legal_workbench.config import get_settings
from legal_workbench.infrastructure.secrets import LocalSecretProvider
from legal_workbench.infrastructure.unit_of_work import SqlAlchemyUnitOfWorkFactory
from legal_workbench.integrations.feishu_local_connector import LocalFeishuConnector
from legal_workbench.integrations.feishu_user_client import FeishuUserClient
from legal_workbench.integrations.feishu_user_oauth import FeishuOAuthHttpClient

PERSONAL_CAPABILITY_KEYS = (
    "oauth_pkce",
    "refresh_rotation",
    "known_p2p_history",
    "known_group_history",
    "group_discovery",
    "p2p_discovery",
    "unread_state",
    "personal_attachment",
    "document_search",
    "document_markdown",
    "thread_reply",
    "local_feishu_discovery",
    "local_api_duplicate_idempotency",
)


def _first_document_token(value: object) -> str | None:
    if not isinstance(value, tuple) or not value:
        return None
    documents = value[0]
    if not isinstance(documents, tuple):
        return None
    for document in documents:
        if not isinstance(document, dict):
            continue
        token = str(
            document.get("doc_token")
            or document.get("document_token")
            or document.get("token")
            or ""
        ).strip()
        if token:
            return token
    return None


class CapabilityResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    capability: str
    status: Literal["passed", "failed", "partial", "unsupported"]
    reason: str


class CapabilityReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    generated_at: datetime
    real_feishu: bool
    identity_source: str
    cli_token_used: bool
    operational_readiness: dict[str, str]
    results: tuple[CapabilityResult, ...]


def build_unavailable_report(*, reason: str) -> CapabilityReport:
    return CapabilityReport(
        generated_at=datetime.now(UTC),
        real_feishu=False,
        identity_source="unavailable",
        cli_token_used=False,
        operational_readiness={
            "Identity": "unsupported",
            "Messages": "unsupported",
            "Chat discovery": "unsupported",
            "Documents": "unsupported",
        },
        results=tuple(
            CapabilityResult(
                capability=capability,
                status="unsupported",
                reason=reason,
            )
            for capability in PERSONAL_CAPABILITY_KEYS
        ),
    )


async def run_live_report(
    *,
    authorization_id: UUID,
    known_p2p_chat_id: str | None,
    known_group_chat_id: str | None,
    attachment_message_id: str | None,
    document_query: str | None,
    document_token: str | None,
    thread_id: str | None,
) -> CapabilityReport:
    settings = get_settings()
    uow_factory = SqlAlchemyUnitOfWorkFactory()
    secrets = LocalSecretProvider(settings.setup_secret_root)
    async with uow_factory() as uow:
        authorization = await uow.feishu_user_authorizations.get_authorization(
            authorization_id
        )
        app_id_setting = await uow.setup.get_setting("feishu.app_id")
        credential = await uow.setup.get_credential(
            provider="feishu", credential_kind="app_secret"
        )
    if authorization is None:
        raise RuntimeError("Authorization metadata was not found.")
    app_id = (
        str(app_id_setting.value)
        if app_id_setting is not None
        else str(settings.feishu_app_id or "")
    ).strip()
    app_secret = str(settings.feishu_app_secret or "").strip()
    if not app_secret and credential and credential.secret_ref:
        app_secret = secrets.read(credential.secret_ref)
    if not app_id or not app_secret:
        raise RuntimeError("Feishu App credentials are not configured.")

    results: dict[str, CapabilityResult] = {
        key: CapabilityResult(
            capability=key,
            status="unsupported",
            reason="manual_validation_required:probe_input_missing",
        )
        for key in PERSONAL_CAPABILITY_KEYS
    }
    results["oauth_pkce"] = CapabilityResult(
        capability="oauth_pkce",
        status=(
            "passed"
            if authorization.status.value == "connected"
            else "partial"
            if authorization.status.value == "permission_missing"
            else "failed"
        ),
        reason=f"authorization_status:{authorization.status.value}",
    )
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(settings.feishu_request_timeout_seconds)
    ) as http_client:
        oauth_client = FeishuOAuthHttpClient(
            app_id=app_id,
            app_secret=app_secret,
            http_client=http_client,
            base_url=settings.feishu_api_base_url.removesuffix("/open-apis"),
        )
        provider = FeishuUserTokenProvider(
            uow_factory,
            oauth_client=oauth_client,
            secret_provider=secrets,
        )
        client = FeishuUserClient(
            token_provider=provider,
            http_client=http_client,
            base_url=settings.feishu_api_base_url,
        )

        async def record(key: str, operation: Awaitable[object]) -> object | None:
            try:
                value = await operation
            except Exception as exc:
                error_code = getattr(exc, "code", type(exc).__name__)
                results[key] = CapabilityResult(
                    capability=key,
                    status="failed",
                    reason=f"official_api_error:{error_code}",
                )
                return None
            results[key] = CapabilityResult(
                capability=key,
                status="passed",
                reason="official_api_executed",
            )
            return value

        await record(
            "refresh_rotation",
            provider.get_access_token(authorization_id, force_refresh=True),
        )
        now = datetime.now(UTC)
        for key, chat_id in (
            ("known_p2p_history", known_p2p_chat_id),
            ("known_group_history", known_group_chat_id),
        ):
            if chat_id:
                await record(
                    key,
                    client.list_messages(
                        authorization_id=authorization_id,
                        chat_id=chat_id,
                        start_time=now.replace(hour=0, minute=0, second=0, microsecond=0),
                        end_time=now,
                        page_token=None,
                    ),
                )
        chats_value = await record(
            "group_discovery",
            client.list_chats(authorization_id=authorization_id),
        )
        if isinstance(chats_value, tuple):
            chats = chats_value[0]
            p2p_found = any(str(value.get("chat_mode") or "") == "p2p" for value in chats)
            results["p2p_discovery"] = CapabilityResult(
                capability="p2p_discovery",
                status="passed" if p2p_found else "partial",
                reason="p2p_found_in_chat_list" if p2p_found else "no_p2p_enumeration_evidence",
            )
            unread_visible = any(
                "unread_count" in value or "last_message_read_time" in value
                for value in chats
            )
            results["unread_state"] = CapabilityResult(
                capability="unread_state",
                status="passed" if unread_visible else "unsupported",
                reason=(
                    "unread_field_visible"
                    if unread_visible
                    else "manual_validation_required:unread_field_not_returned"
                ),
            )
        if attachment_message_id:
            attachment = await record(
                "personal_attachment",
                client.get_message(
                    authorization_id=authorization_id,
                    message_id=attachment_message_id,
                ),
            )
            if isinstance(attachment, dict):
                body = attachment.get("body")
                body_object = body if isinstance(body, dict) else {}
                raw_content = body_object.get("content", attachment.get("content", {}))
                try:
                    content = (
                        json.loads(raw_content)
                        if isinstance(raw_content, str)
                        else raw_content
                    )
                except json.JSONDecodeError:
                    content = {}
                content_object = content if isinstance(content, dict) else {}
                file_key = str(
                    content_object.get("file_key")
                    or content_object.get("image_key")
                    or ""
                ).strip()
                resource_type = (
                    "image"
                    if str(attachment.get("msg_type") or attachment.get("message_type"))
                    == "image"
                    else "file"
                )
                if file_key:
                    value = await record(
                        "personal_attachment",
                        client.download_message_resource(
                            authorization_id=authorization_id,
                            message_id=attachment_message_id,
                            file_key=file_key,
                            resource_type=resource_type,
                        ),
                    )
                    if value is None:
                        results["personal_attachment"] = CapabilityResult(
                            capability="personal_attachment",
                            status="partial",
                            reason="metadata_only:resource_unavailable_under_user_identity",
                        )
                else:
                    results["personal_attachment"] = CapabilityResult(
                        capability="personal_attachment",
                        status="partial",
                        reason="message_visible_but_attachment_key_missing",
                    )
        discovered_document_token: str | None = None
        if document_query:
            document_search_value = await record(
                "document_search",
                client.search_documents(
                    authorization_id=authorization_id,
                    query=document_query,
                ),
            )
            discovered_document_token = _first_document_token(document_search_value)
        markdown_token = document_token or discovered_document_token
        if markdown_token:
            await record(
                "document_markdown",
                client.get_document_markdown(
                    authorization_id=authorization_id,
                    document_id=markdown_token,
                ),
            )
        if thread_id:
            await record(
                "thread_reply",
                client.list_thread_messages(
                    authorization_id=authorization_id,
                    thread_id=thread_id,
                    page_token=None,
                ),
            )
    local_report = LocalFeishuConnector().discover()
    results["local_feishu_discovery"] = CapabilityResult(
        capability="local_feishu_discovery",
        status=(
            "passed"
            if local_report.client_installed and local_report.roots_readable > 0
            else "failed"
        ),
        reason=(
            "read_only_discovery_executed:"
            f"databases={local_report.database_files}:"
            f"readable_messages={local_report.readable_message_databases}:"
            f"opaque={local_report.opaque_or_encrypted_databases}"
        ),
    )
    results["local_api_duplicate_idempotency"] = CapabilityResult(
        capability="local_api_duplicate_idempotency",
        status=(
            "partial"
            if local_report.readable_message_databases > 0
            else "unsupported"
        ),
        reason=(
            "local_record_selection_required"
            if local_report.readable_message_databases > 0
            else "local_message_schema_unavailable"
        ),
    )
    return CapabilityReport(
        generated_at=datetime.now(UTC),
        real_feishu=True,
        identity_source="workbench_oauth_token_provider",
        cli_token_used=False,
        operational_readiness={
            CAPABILITY_LABELS[capability]: project_capabilities(authorization.scopes)[
                capability
            ].status.value
            for capability in (
                FeishuCapability.CORE_IDENTITY,
                FeishuCapability.MESSAGE_HISTORY,
                FeishuCapability.CHAT_DISCOVERY,
                FeishuCapability.DOCUMENT_READ,
            )
        },
        results=tuple(results[key] for key in PERSONAL_CAPABILITY_KEYS),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate official Feishu personal capabilities")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--authorization-id", type=UUID)
    parser.add_argument("--known-p2p-chat-id")
    parser.add_argument("--known-group-chat-id")
    parser.add_argument("--attachment-message-id")
    parser.add_argument("--document-query")
    parser.add_argument("--document-token")
    parser.add_argument("--thread-id")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.live:
        if args.authorization_id is None:
            parser.error("--live requires --authorization-id")
        report = asyncio.run(
            run_live_report(
                authorization_id=args.authorization_id,
                known_p2p_chat_id=args.known_p2p_chat_id,
                known_group_chat_id=args.known_group_chat_id,
                attachment_message_id=args.attachment_message_id,
                document_query=args.document_query,
                document_token=args.document_token,
                thread_id=args.thread_id,
            )
        )
    else:
        report = build_unavailable_report(
            reason="live_flag_and_real_credentials_required"
        )
    rendered = report.model_dump_json(indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)


if __name__ == "__main__":
    main()
