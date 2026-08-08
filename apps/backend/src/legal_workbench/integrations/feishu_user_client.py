from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

import httpx

from legal_workbench.integrations.feishu_user_oauth import FeishuUserApiError


@dataclass(frozen=True, slots=True)
class UserMessagePage:
    items: tuple[dict[str, object], ...]
    next_page_token: str | None


class UserAccessTokenProvider(Protocol):
    async def get_access_token(
        self, authorization_id: UUID, *, force_refresh: bool = False
    ) -> str: ...


class FeishuUserClient:
    """Official Feishu User API client; it never returns or logs credentials."""

    def __init__(
        self,
        *,
        token_provider: UserAccessTokenProvider,
        http_client: httpx.AsyncClient,
        base_url: str = "https://open.feishu.cn/open-apis",
        sleep: object = asyncio.sleep,
        max_attempts: int = 3,
    ) -> None:
        self._token_provider = token_provider
        self._http_client = http_client
        self._base_url = base_url.rstrip("/")
        self._sleep = sleep
        self._max_attempts = max_attempts

    async def list_messages(
        self,
        *,
        authorization_id: UUID,
        chat_id: str,
        start_time: datetime,
        end_time: datetime,
        page_token: str | None,
    ) -> UserMessagePage:
        params: dict[str, str | int] = {
            "container_id_type": "chat",
            "container_id": chat_id,
            "start_time": int(start_time.timestamp()),
            "end_time": int(end_time.timestamp()),
            "sort_type": "ByCreateTimeAsc",
            "page_size": 50,
        }
        if page_token:
            params["page_token"] = page_token
        data = await self._request(
            authorization_id=authorization_id,
            method="GET",
            path="/im/v1/messages",
            params=params,
        )
        items = data.get("items")
        normalized_items = tuple(item for item in items if isinstance(item, dict)) if isinstance(
            items, list
        ) else ()
        next_page = str(data.get("page_token") or "").strip() or None
        if bool(data.get("has_more")) and next_page is None:
            raise FeishuUserApiError(code="missing_page_token", http_status=200)
        return UserMessagePage(items=normalized_items, next_page_token=next_page)

    async def get_message(
        self, *, authorization_id: UUID, message_id: str
    ) -> dict[str, object]:
        data = await self._request(
            authorization_id=authorization_id,
            method="GET",
            path=f"/im/v1/messages/{message_id}",
        )
        items = data.get("items")
        if isinstance(items, list) and items and isinstance(items[0], dict):
            return items[0]
        raise FeishuUserApiError(code="message_not_found", http_status=200)

    async def list_chats(
        self, *, authorization_id: UUID, page_token: str | None = None
    ) -> tuple[tuple[dict[str, object], ...], str | None]:
        params: dict[str, str | int] = {"page_size": 100}
        if page_token:
            params["page_token"] = page_token
        data = await self._request(
            authorization_id=authorization_id,
            method="GET",
            path="/im/v1/chats",
            params=params,
        )
        items = data.get("items")
        values = tuple(item for item in items if isinstance(item, dict)) if isinstance(
            items, list
        ) else ()
        next_page = str(data.get("page_token") or "").strip() or None
        return values, next_page

    async def search_documents(
        self,
        *,
        authorization_id: UUID,
        query: str,
        page_token: str | None = None,
    ) -> tuple[tuple[dict[str, object], ...], str | None]:
        body: dict[str, object] = {"search_key": query, "count": 50}
        if page_token:
            body["offset"] = page_token
        data = await self._request(
            authorization_id=authorization_id,
            method="POST",
            path="/suite/docs-api/search/object",
            json_body=body,
        )
        docs = data.get("docs_entities")
        values = tuple(item for item in docs if isinstance(item, dict)) if isinstance(
            docs, list
        ) else ()
        next_page = str(data.get("offset") or "").strip() or None
        return values, next_page

    async def get_document_markdown(
        self, *, authorization_id: UUID, document_id: str
    ) -> str:
        data = await self._request(
            authorization_id=authorization_id,
            method="GET",
            path="/docs/v1/content",
            params={"doc_token": document_id, "doc_type": "docx", "content_type": "markdown"},
        )
        content = data.get("content")
        if not isinstance(content, str):
            raise FeishuUserApiError(code="markdown_unavailable", http_status=200)
        return content

    async def list_folder_files(
        self,
        *,
        authorization_id: UUID,
        folder_token: str,
        page_token: str | None = None,
    ) -> tuple[tuple[dict[str, object], ...], str | None]:
        params: dict[str, str | int] = {
            "folder_token": folder_token,
            "page_size": 200,
        }
        if page_token:
            params["page_token"] = page_token
        data = await self._request(
            authorization_id=authorization_id,
            method="GET",
            path="/drive/v1/files",
            params=params,
        )
        files = data.get("files")
        values = tuple(item for item in files if isinstance(item, dict)) if isinstance(
            files, list
        ) else ()
        next_page = str(data.get("next_page_token") or "").strip() or None
        return values, next_page

    async def _request(
        self,
        *,
        authorization_id: UUID,
        method: str,
        path: str,
        params: dict[str, str | int] | None = None,
        json_body: dict[str, object] | None = None,
    ) -> dict[str, Any]:
        force_refresh = False
        refreshed_after_unauthorized = False
        for attempt in range(1, self._max_attempts + 1):
            if force_refresh:
                access_token = await self._token_provider.get_access_token(
                    authorization_id, force_refresh=True
                )
                force_refresh = False
            else:
                access_token = await self._token_provider.get_access_token(authorization_id)
            response = await self._http_client.request(
                method,
                f"{self._base_url}{path}",
                params=params,
                json=json_body,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if response.status_code == 401 and not refreshed_after_unauthorized:
                refreshed_after_unauthorized = True
                force_refresh = True
                continue
            if response.status_code == 429 and attempt < self._max_attempts:
                retry_after = self._retry_after(response, attempt)
                await self._sleep(retry_after)  # type: ignore[operator]
                continue
            payload = self._parse_response(response)
            data = payload.get("data", {})
            if not isinstance(data, dict):
                raise FeishuUserApiError(code="invalid_response", http_status=response.status_code)
            return data
        raise FeishuUserApiError(code="retry_exhausted", http_status=429)

    @staticmethod
    def _retry_after(response: httpx.Response, attempt: int) -> float:
        try:
            return max(0.0, min(float(response.headers.get("Retry-After", "")), 60.0))
        except ValueError:
            return float(min(2 ** (attempt - 1), 30))

    @staticmethod
    def _parse_response(response: httpx.Response) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError as exc:
            raise FeishuUserApiError(
                code="invalid_response", http_status=response.status_code
            ) from exc
        code = payload.get("code", 0) if isinstance(payload, dict) else "invalid_response"
        if response.is_error or code != 0:
            raise FeishuUserApiError(code=code, http_status=response.status_code)
        if not isinstance(payload, dict):
            raise FeishuUserApiError(code="invalid_response", http_status=response.status_code)
        return payload
