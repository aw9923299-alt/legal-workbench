from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass


class InvalidSessionError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class RequestActor:
    actor_id: str
    identity_source: str


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def create_session_token(
    *,
    actor_id: str,
    identity_source: str,
    secret: str,
    ttl_seconds: int,
    now: int | None = None,
) -> str:
    issued_at = int(time.time()) if now is None else now
    payload = json.dumps(
        {
            "sub": actor_id,
            "src": identity_source,
            "iat": issued_at,
            "exp": issued_at + ttl_seconds,
            "v": 1,
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    encoded = _encode(payload)
    signature = hmac.new(secret.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256)
    return f"{encoded}.{_encode(signature.digest())}"


def decode_session_token(*, token: str, secret: str, now: int | None = None) -> RequestActor:
    try:
        encoded, provided_signature = token.split(".", 1)
        expected_signature = hmac.new(
            secret.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256
        ).digest()
        if not hmac.compare_digest(_decode(provided_signature), expected_signature):
            raise InvalidSessionError("Session signature is invalid.")
        payload = json.loads(_decode(encoded))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        if isinstance(exc, InvalidSessionError):
            raise
        raise InvalidSessionError("Session token is malformed.") from exc
    current_time = int(time.time()) if now is None else now
    if not isinstance(payload, dict) or payload.get("v") != 1:
        raise InvalidSessionError("Session version is invalid.")
    actor_id = payload.get("sub")
    identity_source = payload.get("src")
    expires_at = payload.get("exp")
    if not isinstance(actor_id, str) or not actor_id.strip():
        raise InvalidSessionError("Session actor is invalid.")
    if not isinstance(identity_source, str) or not identity_source.strip():
        raise InvalidSessionError("Session identity source is invalid.")
    if not isinstance(expires_at, int) or expires_at <= current_time:
        raise InvalidSessionError("Session has expired.")
    return RequestActor(actor_id=actor_id, identity_source=identity_source)
