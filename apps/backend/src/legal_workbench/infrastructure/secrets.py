from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from legal_workbench.domain.errors import DomainValidationError

_REFERENCE_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,79}$")


@dataclass(frozen=True, slots=True)
class TokenGenerationSecret:
    access_token: str
    refresh_token: str
    access_expires_at: datetime
    refresh_expires_at: datetime
    scopes: tuple[str, ...]

    def __repr__(self) -> str:
        return (
            "TokenGenerationSecret(access_token=<redacted>, "
            "refresh_token=<redacted>, "
            f"access_expires_at={self.access_expires_at!r}, "
            f"refresh_expires_at={self.refresh_expires_at!r}, "
            f"scopes={self.scopes!r})"
        )


class LocalSecretProvider:
    """Store local integration secrets outside PostgreSQL and Codex run roots."""

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root).resolve()

    def __repr__(self) -> str:
        return f"LocalSecretProvider(root={self._root!s})"

    @staticmethod
    def masked_hint(value: str) -> str:
        suffix = value[-4:] if len(value) >= 4 else "••••"
        return f"••••{suffix}"

    def exists(self, reference: str) -> bool:
        return self._path(reference).is_file()

    def read(self, reference: str) -> str:
        try:
            return self._path(reference).read_text(encoding="utf-8")
        except OSError as exc:
            raise DomainValidationError("The configured local secret is unavailable.") from exc

    def write(self, reference: str, value: str) -> str:
        secret = value.strip()
        if not secret:
            raise DomainValidationError("A non-empty secret value is required.")
        target = self._path(reference)
        self._root.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self._root, 0o700)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{reference}-",
            suffix=".tmp",
            dir=self._root,
            text=True,
        )
        temporary = Path(temporary_name)
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                stream.write(secret)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)
            os.chmod(target, 0o600)
            directory_descriptor = os.open(self._root, os.O_RDONLY)
            try:
                os.fsync(directory_descriptor)
            finally:
                os.close(directory_descriptor)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
        return reference

    def delete(self, reference: str) -> None:
        target = self._path(reference)
        try:
            target.unlink(missing_ok=True)
        except OSError as exc:
            raise DomainValidationError(
                "The configured local secret could not be removed."
            ) from exc

    def write_token_generation(
        self,
        reference: str,
        *,
        access_token: str,
        refresh_token: str,
        access_expires_at: datetime,
        refresh_expires_at: datetime,
        scopes: tuple[str, ...],
    ) -> str:
        if access_expires_at.tzinfo is None or refresh_expires_at.tzinfo is None:
            raise DomainValidationError("Token generation expiry must include a timezone.")
        payload = json.dumps(
            {
                "accessToken": access_token,
                "refreshToken": refresh_token,
                "accessExpiresAt": access_expires_at.isoformat(),
                "refreshExpiresAt": refresh_expires_at.isoformat(),
                "scopes": list(scopes),
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return self.write(reference, payload)

    def read_token_generation(self, reference: str) -> TokenGenerationSecret:
        try:
            payload = json.loads(self.read(reference))
            if not isinstance(payload, dict):
                raise ValueError
            access_token = payload["accessToken"]
            refresh_token = payload["refreshToken"]
            scopes = payload["scopes"]
            if (
                not isinstance(access_token, str)
                or not isinstance(refresh_token, str)
                or not isinstance(scopes, list)
                or not all(isinstance(value, str) for value in scopes)
            ):
                raise ValueError
            value = TokenGenerationSecret(
                access_token=access_token,
                refresh_token=refresh_token,
                access_expires_at=datetime.fromisoformat(str(payload["accessExpiresAt"])),
                refresh_expires_at=datetime.fromisoformat(
                    str(payload["refreshExpiresAt"])
                ),
                scopes=tuple(scopes),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise DomainValidationError("Token generation secret is invalid.") from exc
        if value.access_expires_at.tzinfo is None or value.refresh_expires_at.tzinfo is None:
            raise DomainValidationError("Token generation expiry must include a timezone.")
        return value

    def _path(self, reference: str) -> Path:
        if not _REFERENCE_PATTERN.fullmatch(reference):
            raise DomainValidationError("Secret reference is invalid.")
        target = (self._root / f"{reference}.secret").resolve()
        if target.parent != self._root:
            raise DomainValidationError("Secret reference escapes the configured root.")
        return target
