from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256

from legal_workbench.domain.errors import (
    DomainValidationError,
)


def utc_now() -> datetime:
    return datetime.now(UTC)


def text_hash(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def require_aware(value: datetime, *, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise DomainValidationError(f"{field_name} must be timezone-aware.")
