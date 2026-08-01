from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta

import httpx

from legal_workbench.config import Settings, get_settings
from legal_workbench.domain.entities import Communication


class FeishuApiError(RuntimeError):
    pass


class FeishuApiClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._token: str | None = None
        self._token_expires_at: datetime | None = None
        self._token_lock = asyncio.Lock()

    async def send_communication(self, communication: Communication) -> str:
        if not self._settings.enable_external_send:
            raise FeishuApiError("External send is disabled by configuration.")
        token = await self._get_tenant_access_token()
        target = communication.target
        reply_to = str(target.get("replyToMessageId") or "").strip()
        msg_type = str(target.get("messageType") or "text")
        content = self._build_content(msg_type, communication.content)
        headers = {"Authorization": f"Bearer {token}"}
        timeout = httpx.Timeout(self._settings.feishu_request_timeout_seconds)
        async with httpx.AsyncClient(
            base_url=self._settings.feishu_api_base_url,
            headers=headers,
            timeout=timeout,
        ) as client:
            if reply_to:
                response = await client.post(
                    f"/im/v1/messages/{reply_to}/reply",
                    json={
                        "msg_type": msg_type,
                        "content": content,
                        "uuid": str(communication.id),
                    },
                )
            else:
                receive_id = str(target.get("receiveId") or "").strip()
                receive_id_type = str(target.get("receiveIdType") or "open_id").strip()
                if not receive_id:
                    raise FeishuApiError("Communication target.receiveId is required.")
                response = await client.post(
                    "/im/v1/messages",
                    params={"receive_id_type": receive_id_type},
                    json={
                        "receive_id": receive_id,
                        "msg_type": msg_type,
                        "content": content,
                        "uuid": str(communication.id),
                    },
                )
        return self._extract_message_id(response)

    async def _get_tenant_access_token(self) -> str:
        now = datetime.now(UTC)
        if self._token and self._token_expires_at and self._token_expires_at > now:
            return self._token
        async with self._token_lock:
            now = datetime.now(UTC)
            if self._token and self._token_expires_at and self._token_expires_at > now:
                return self._token
            if not self._settings.feishu_app_id or not self._settings.feishu_app_secret:
                raise FeishuApiError("Feishu app credentials are not configured.")
            timeout = httpx.Timeout(self._settings.feishu_request_timeout_seconds)
            async with httpx.AsyncClient(
                base_url=self._settings.feishu_api_base_url,
                timeout=timeout,
            ) as client:
                response = await client.post(
                    "/auth/v3/tenant_access_token/internal",
                    json={
                        "app_id": self._settings.feishu_app_id,
                        "app_secret": self._settings.feishu_app_secret,
                    },
                )
            data = self._parse_response(response)
            token = str(data.get("tenant_access_token") or "")
            if not token:
                raise FeishuApiError("Feishu token response did not contain a token.")
            expires_in = int(data.get("expire") or 7200)
            self._token = token
            self._token_expires_at = now + timedelta(seconds=max(60, expires_in - 120))
            return token

    @staticmethod
    def _build_content(msg_type: str, content: str) -> str:
        if msg_type == "text":
            return json.dumps({"text": content}, ensure_ascii=False)
        return content

    @classmethod
    def _extract_message_id(cls, response: httpx.Response) -> str:
        data = cls._parse_response(response)
        message_data = data.get("data")
        if not isinstance(message_data, dict):
            raise FeishuApiError("Feishu send response did not contain data.")
        message_id = str(message_data.get("message_id") or "")
        if not message_id:
            raise FeishuApiError("Feishu send response did not contain message_id.")
        return message_id

    @staticmethod
    def _parse_response(response: httpx.Response) -> dict[str, object]:
        try:
            data = response.json()
        except ValueError as exc:
            raise FeishuApiError(
                f"Feishu returned a non-JSON response ({response.status_code})."
            ) from exc
        if response.is_error:
            raise FeishuApiError(
                f"Feishu HTTP error {response.status_code}: {data}"
            )
        if not isinstance(data, dict):
            raise FeishuApiError("Feishu returned an invalid response body.")
        code = int(data.get("code") or 0)
        if code != 0:
            raise FeishuApiError(
                f"Feishu API error {code}: {data.get('msg') or 'unknown error'}"
            )
        return data
