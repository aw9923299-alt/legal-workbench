from dataclasses import dataclass
from uuid import UUID

from legal_workbench.domain.enums import CandidateStatus


@dataclass(frozen=True, slots=True)
class CandidateCreatedResult:
    candidate_id: UUID
    version: int
    idempotent_replay: bool = False


@dataclass(frozen=True, slots=True)
class MatterCreatedResult:
    matter_id: UUID
    matter_number: str
    work_item_ids: list[UUID]
    idempotent_replay: bool = False


@dataclass(frozen=True, slots=True)
class CandidateResolvedResult:
    candidate_id: UUID
    status: CandidateStatus
    matter_id: UUID | None
    version: int
    idempotent_replay: bool = False


@dataclass(frozen=True, slots=True)
class WorkItemCreatedResult:
    work_item_id: UUID
    matter_id: UUID
    idempotent_replay: bool = False


@dataclass(frozen=True, slots=True)
class PriorityConfirmedResult:
    work_item_id: UUID
    confirmation_id: UUID
    version: int
    idempotent_replay: bool = False


@dataclass(frozen=True, slots=True)
class DeadlineCreatedResult:
    deadline_id: UUID
    idempotent_replay: bool = False


@dataclass(frozen=True, slots=True)
class DependencyCreatedResult:
    dependency_id: UUID
    work_item_version: int
    idempotent_replay: bool = False


@dataclass(frozen=True, slots=True)
class ReviewPackageCreatedResult:
    review_package_id: UUID
    version: int
    idempotent_replay: bool = False


@dataclass(frozen=True, slots=True)
class ReviewRecordedResult:
    review_package_id: UUID
    review_record_id: UUID
    status: str
    idempotent_replay: bool = False


@dataclass(frozen=True, slots=True)
class CommunicationQueuedResult:
    communication_id: UUID
    status: str
    idempotent_replay: bool = False


@dataclass(frozen=True, slots=True)
class FeishuEventIngestedResult:
    event_id: UUID
    message_id: UUID | None
    duplicate: bool
