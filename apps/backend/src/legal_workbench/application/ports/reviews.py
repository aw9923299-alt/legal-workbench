from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol
from uuid import UUID

from legal_workbench.domain.enums import (
    CommunicationStatus,
    ReviewPackageStatus,
)
from legal_workbench.domain.reviews import (
    Communication,
    ReviewPackage,
    ReviewRecord,
)

__all__ = [
    "CommunicationRepository",
    "ReviewPackageRepository",
    "ReviewRecordRepository",
]


class ReviewPackageRepository(Protocol):
    async def add(self, package: ReviewPackage) -> None: ...
    async def get(self, package_id: UUID) -> ReviewPackage | None: ...
    async def get_for_update(self, package_id: UUID) -> ReviewPackage | None: ...
    async def save(self, package: ReviewPackage) -> None: ...
    async def list(
        self, *, status: ReviewPackageStatus | None, matter_id: UUID | None, limit: int
    ) -> Sequence[ReviewPackage]: ...


class ReviewRecordRepository(Protocol):
    async def add(self, record: ReviewRecord) -> None: ...
    async def get(self, record_id: UUID) -> ReviewRecord | None: ...
    async def get_latest_approved(self, package_id: UUID) -> ReviewRecord | None: ...
    async def list_by_package(self, package_id: UUID) -> Sequence[ReviewRecord]: ...


class CommunicationRepository(Protocol):
    async def add(self, communication: Communication) -> None: ...
    async def get(self, communication_id: UUID) -> Communication | None: ...
    async def get_for_update(self, communication_id: UUID) -> Communication | None: ...
    async def get_by_review_record(self, review_record_id: UUID) -> Communication | None: ...
    async def list_sent_by_external_message_ids(
        self, external_message_ids: Sequence[str]
    ) -> Sequence[Communication]: ...
    async def list(
        self, *, status: CommunicationStatus | None, limit: int
    ) -> Sequence[Communication]: ...
