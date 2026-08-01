from collections.abc import Sequence
from uuid import UUID

from legal_workbench.application.ports import UnitOfWorkFactory
from legal_workbench.domain.entities import (
    Communication,
    Deadline,
    LegalMatter,
    MessageCandidate,
    PriorityConfirmation,
    ReviewPackage,
    ReviewRecord,
    WorkItem,
    WorkItemDependency,
)
from legal_workbench.domain.enums import (
    CandidateStatus,
    CommunicationStatus,
    DeadlineStatus,
    ReviewPackageStatus,
)
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


class WorkItemQueryService:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def get(self, work_item_id: UUID) -> WorkItem:
        async with self._uow_factory() as uow:
            work_item = await uow.work_items.get(work_item_id)
            if work_item is None:
                raise EntityNotFoundError(
                    "Work item was not found.",
                    details={"workItemId": str(work_item_id)},
                )
            return work_item

    async def list_priority_confirmations(
        self, work_item_id: UUID
    ) -> Sequence[PriorityConfirmation]:
        async with self._uow_factory() as uow:
            if await uow.work_items.get(work_item_id) is None:
                raise EntityNotFoundError("Work item was not found.")
            return await uow.priority_confirmations.list_by_work_item(work_item_id)

    async def list_deadlines(
        self,
        work_item_id: UUID,
        *,
        status: DeadlineStatus | None = None,
    ) -> Sequence[Deadline]:
        async with self._uow_factory() as uow:
            if await uow.work_items.get(work_item_id) is None:
                raise EntityNotFoundError("Work item was not found.")
            return await uow.deadlines.list_by_work_item(work_item_id, status=status)

    async def list_dependencies(
        self, work_item_id: UUID
    ) -> Sequence[WorkItemDependency]:
        async with self._uow_factory() as uow:
            if await uow.work_items.get(work_item_id) is None:
                raise EntityNotFoundError("Work item was not found.")
            return await uow.dependencies.list_by_work_item(work_item_id)


class ReviewQueryService:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def get_package(self, package_id: UUID) -> ReviewPackage:
        async with self._uow_factory() as uow:
            package = await uow.review_packages.get(package_id)
            if package is None:
                raise EntityNotFoundError("Review package was not found.")
            return package

    async def list_packages(
        self,
        *,
        status: ReviewPackageStatus | None = None,
        matter_id: UUID | None = None,
        limit: int = 50,
    ) -> Sequence[ReviewPackage]:
        async with self._uow_factory() as uow:
            return await uow.review_packages.list(
                status=status, matter_id=matter_id, limit=limit
            )

    async def list_records(self, package_id: UUID) -> Sequence[ReviewRecord]:
        async with self._uow_factory() as uow:
            if await uow.review_packages.get(package_id) is None:
                raise EntityNotFoundError("Review package was not found.")
            return await uow.review_records.list_by_package(package_id)

    async def list_communications(
        self,
        *,
        status: CommunicationStatus | None = None,
        limit: int = 50,
    ) -> Sequence[Communication]:
        async with self._uow_factory() as uow:
            return await uow.communications.list(status=status, limit=limit)
