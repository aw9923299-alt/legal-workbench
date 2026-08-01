from dataclasses import dataclass
from uuid import UUID


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
class WorkItemCreatedResult:
    work_item_id: UUID
    matter_id: UUID
    idempotent_replay: bool = False
