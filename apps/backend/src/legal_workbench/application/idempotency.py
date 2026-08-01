from __future__ import annotations

import hashlib
import json
from typing import Any
from uuid import UUID

from legal_workbench.domain.entities import IdempotencyRecord
from legal_workbench.domain.errors import IdempotencyConflictError


def request_hash(payload: dict[str, Any]) -> str:
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def require_matching_replay(
    record: IdempotencyRecord | None,
    *,
    expected_hash: str,
    idempotency_key: str,
) -> IdempotencyRecord | None:
    if record is None:
        return None
    if record.request_hash != expected_hash:
        raise IdempotencyConflictError(
            "The idempotency key was already used for a different request.",
            details={"idempotencyKey": idempotency_key},
        )
    return record


def replay_uuid(record: IdempotencyRecord, field: str) -> UUID:
    return UUID(str(record.response_payload[field]))
