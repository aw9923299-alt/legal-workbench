from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from legal_workbench.application.feishu_user_auth import (
    FeishuOAuthTokens,
    OAuthIdentity,
)


class FeishuUserApiError(RuntimeError):
    def __init__(self, *, code: int | str, http_status: int) -> None:
        self.code = code
        self.http_status = http_status
        super().__init__(f"Feishu user API request failed (code={code}, status={http_status}).")


class FeishuOAuthHttpClient:
    def __init__(
        self,
        *,
        app_id: str,
        app_secret: str,
        http_client: httpx.AsyncClient,
        base_url: str = "https://open.feishu.cn",
    ) -> None:
        self._app_id = app_id
        self._app_secret = app_secret
        self._http_client = http_client
        self._base_url = base_url.rstrip("/")

    async def exchange_code(self, *, code: str, code_verifier: str) -> FeishuOAuthTokens:
        payload = await self._post_token(
            {
                "grant_type": "authorization_code",
                "client_id": self._app_id,
                "client_secret": self._app_secret,
                "code": code,
                "code_verifier": code_verifier,
            }
        )
        return self._parse_tokens(payload)

    async def refresh(self, *, refresh_token: str) -> FeishuOAuthTokens:
        payload = await self._post_token(
            {
                "grant_type": "refresh_token",
                "client_id": self._app_id,
                "client_secret": self._app_secret,
                "refresh_token": refresh_token,
            }
        )
        return self._parse_tokens(payload)

    async def get_identity(self, *, access_token: str) -> OAuthIdentity:
        response = await self._http_client.get(
            f"{self._base_url}/open-apis/authen/v1/user_info",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        payload = self._parse_response(response)
        data = self._data(payload)
        return OAuthIdentity(
            open_id=str(data.get("open_id") or ""),
            union_id=self._optional_string(data.get("union_id")),
            tenant_key=str(data.get("tenant_key") or ""),
            display_name=self._optional_string(data.get("name")),
        )

    async def _post_token(self, body: dict[str, str]) -> dict[str, Any]:
        response = await self._http_client.post(
            f"{self._base_url}/open-apis/authen/v2/oauth/token",
            json=body,
        )
        return self._parse_response(response)

    @staticmethod
    def _parse_response(response: httpx.Response) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError as exc:
            raise FeishuUserApiError(
                code="invalid_response",
                http_status=response.status_code,
            ) from exc
        code = payload.get("code", 0) if isinstance(payload, dict) else "invalid_response"
        if response.is_error or code != 0:
            raise FeishuUserApiError(code=code, http_status=response.status_code)
        if not isinstance(payload, dict):
            raise FeishuUserApiError(
                code="invalid_response",
                http_status=response.status_code,
            )
        return payload

    @staticmethod
    def _data(payload: dict[str, Any]) -> dict[str, Any]:
        data = payload.get("data", payload)
        if not isinstance(data, dict):
            raise FeishuUserApiError(code="invalid_response", http_status=200)
        return data

    @classmethod
    def _parse_tokens(cls, payload: dict[str, Any]) -> FeishuOAuthTokens:
        data = cls._data(payload)
        try:
            access_token = str(data["access_token"])
            refresh_token = str(data["refresh_token"])
            expires_in = int(data["expires_in"])
            refresh_expires_in = int(data["refresh_expires_in"])
        except (KeyError, TypeError, ValueError) as exc:
            raise FeishuUserApiError(code="invalid_response", http_status=200) from exc
        raw_scope = data.get("scope", "")
        scopes = tuple(
            scope for scope in str(raw_scope).replace(",", " ").split() if scope
        )
        issued_at = datetime.now(UTC)
        return FeishuOAuthTokens(
            access_token=access_token,
            refresh_token=refresh_token,
            access_expires_at=issued_at + timedelta(seconds=expires_in),
            refresh_expires_at=issued_at + timedelta(seconds=refresh_expires_in),
            scopes=scopes,
        )

    @staticmethod
    def _optional_string(value: object) -> str | None:
        normalized = str(value).strip() if value is not None else ""
        return normalized or None
