from collections.abc import Sequence
from uuid import UUID

from legal_workbench.application.ports import UnitOfWorkFactory
from legal_workbench.domain.entities import LegalMatter, MessageCandidate, WorkItem
from legal_workbench.domain.enums import CandidateStatus
from legal_workbench.domain.errors import EntityNotFoundError


class CandidateQueryService:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def get(self, candidate_id: UUID) -> MessageCandidate:
        async with self._uow_factory() as uow:
            candidate = await uow.candidates.get(candidate_id)
            if candidate is None:
                raise EntityNotFoundError(
                    "Message candidate was not found.",
                    details={"candidateId": str(candidate_id)},
                )
            return candidate

    async def list(
        self, *, status: CandidateStatus | None, limit: int
    ) -> Sequence[MessageCandidate]:
        async with self._uow_factory() as uow:
            return await uow.candidates.list(status=status, limit=limit)


class MatterQueryService:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def get(self, matter_id: UUID) -> LegalMatter:
        async with self._uow_factory() as uow:
            matter = await uow.matters.get(matter_id)
            if matter is None:
                raise EntityNotFoundError(
                    "Legal matter was not found.",
                    details={"matterId": str(matter_id)},
                )
            return matter

    async def list(self, *, owner_id: str | None, limit: int) -> Sequence[LegalMatter]:
        async with self._uow_factory() as uow:
            return await uow.matters.list(owner_id=owner_id, limit=limit)

    async def list_work_items(self, matter_id: UUID) -> Sequence[WorkItem]:
        async with self._uow_factory() as uow:
            matter = await uow.matters.get(matter_id)
            if matter is None:
                raise EntityNotFoundError(
                    "Legal matter was not found.",
                    details={"matterId": str(matter_id)},
                )
            return await uow.work_items.list_by_matter(matter_id)
