from __future__ import annotations

import argparse
import asyncio
from collections.abc import Awaitable
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import httpx
from pydantic import BaseModel, ConfigDict

from legal_workbench.application.feishu_user_auth import FeishuUserTokenProvider
from legal_workbench.config import get_settings
from legal_workbench.infrastructure.secrets import LocalSecretProvider
from legal_workbench.infrastructure.unit_of_work import SqlAlchemyUnitOfWorkFactory
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
)


class CapabilityResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    capability: str
    status: str
    reason: str


class CapabilityReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    generated_at: datetime
    real_feishu: bool
    results: tuple[CapabilityResult, ...]


def build_not_executed_report(*, reason: str) -> CapabilityReport:
    return CapabilityReport(
        generated_at=datetime.now(UTC),
        real_feishu=False,
        results=tuple(
            CapabilityResult(
                capability=capability,
                status="not_executed",
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
            status="not_executed",
            reason="required_probe_input_missing",
        )
        for key in PERSONAL_CAPABILITY_KEYS
    }
    results["oauth_pkce"] = CapabilityResult(
        capability="oauth_pkce",
        status="passed" if authorization.status.value == "connected" else "failed",
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
                status="passed" if p2p_found else "officially_limited",
                reason="p2p_found_in_chat_list" if p2p_found else "no_p2p_enumeration_evidence",
            )
            unread_visible = any(
                "unread_count" in value or "last_message_read_time" in value
                for value in chats
            )
            results["unread_state"] = CapabilityResult(
                capability="unread_state",
                status="passed" if unread_visible else "officially_limited",
                reason="unread_field_visible" if unread_visible else "unread_field_not_returned",
            )
        if attachment_message_id:
            attachment = await record(
                "personal_attachment",
                client.get_message(
                    authorization_id=authorization_id,
                    message_id=attachment_message_id,
                ),
            )
            if attachment is not None:
                results["personal_attachment"] = CapabilityResult(
                    capability="personal_attachment",
                    status="metadata_only",
                    reason="official_user_resource_download_not_available",
                )
        if document_query:
            await record(
                "document_search",
                client.search_documents(
                    authorization_id=authorization_id,
                    query=document_query,
                ),
            )
        if document_token:
            await record(
                "document_markdown",
                client.get_document_markdown(
                    authorization_id=authorization_id,
                    document_id=document_token,
                ),
            )
    return CapabilityReport(
        generated_at=datetime.now(UTC),
        real_feishu=True,
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
            )
        )
    else:
        report = build_not_executed_report(reason="live_flag_and_real_credentials_required")
    rendered = report.model_dump_json(indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)


if __name__ == "__main__":
    main()
