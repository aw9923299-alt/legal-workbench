from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, status

from legal_workbench.api.dependencies import (
    get_actor_id,
    get_correlation_id,
    get_idempotency_key,
    get_uow_factory,
)
from legal_workbench.api.schemas.matters import WorkItemResponse
from legal_workbench.api.schemas.workflow import (
    ConfirmPriorityRequest,
    CreateDeadlineRequest,
    CreateDependencyRequest,
    DeadlineCreatedResponse,
    DeadlineResponse,
    DependencyCreatedResponse,
    DependencyResponse,
    PriorityConfirmationResponse,
    PriorityConfirmedResponse,
)
from legal_workbench.application.commands import (
    ConfirmPriorityCommand,
    CreateDeadlineCommand,
    CreateDependencyCommand,
)
from legal_workbench.application.queries import WorkItemQueryService
from legal_workbench.application.workflow_handlers import (
    ConfirmPriorityHandler,
    CreateDeadlineHandler,
    CreateDependencyHandler,
)
from legal_workbench.infrastructure.unit_of_work import SqlAlchemyUnitOfWorkFactory

router = APIRouter(prefix="/work-items", tags=["work-items"])


@router.get("/{work_item_id}", response_model=WorkItemResponse)
async def get_work_item(
    work_item_id: UUID,
    uow_factory: Annotated[SqlAlchemyUnitOfWorkFactory, Depends(get_uow_factory)],
) -> WorkItemResponse:
    item = await WorkItemQueryService(uow_factory).get(work_item_id)
    return WorkItemResponse.model_validate(item)


@router.post(
    "/{work_item_id}/priority-confirmations",
    response_model=PriorityConfirmedResponse,
    status_code=status.HTTP_201_CREATED,
)
async def confirm_priority(
    work_item_id: UUID,
    body: ConfirmPriorityRequest,
    request: Request,
    response: Response,
    actor_id: Annotated[str, Depends(get_actor_id)],
    idempotency_key: Annotated[str, Depends(get_idempotency_key)],
    uow_factory: Annotated[SqlAlchemyUnitOfWorkFactory, Depends(get_uow_factory)],
) -> PriorityConfirmedResponse:
    result = await ConfirmPriorityHandler(uow_factory).execute(
        ConfirmPriorityCommand(
            work_item_id=work_item_id,
            work_item_version=body.work_item_version,
            actor_id=actor_id,
            correlation_id=get_correlation_id(request),
            idempotency_key=idempotency_key,
            confirmed_priority=body.confirmed_priority,
            confirmed_complete_at=body.confirmed_complete_at,
            reasons=body.reasons,
            override_reason=body.override_reason,
        )
    )
    if result.idempotent_replay:
        response.status_code = status.HTTP_200_OK
    return PriorityConfirmedResponse.model_validate(result)


@router.get(
    "/{work_item_id}/priority-confirmations",
    response_model=list[PriorityConfirmationResponse],
)
async def list_priority_confirmations(
    work_item_id: UUID,
    uow_factory: Annotated[SqlAlchemyUnitOfWorkFactory, Depends(get_uow_factory)],
) -> list[PriorityConfirmationResponse]:
    values = await WorkItemQueryService(uow_factory).list_priority_confirmations(work_item_id)
    return [PriorityConfirmationResponse.model_validate(value) for value in values]


@router.post(
    "/{work_item_id}/deadlines",
    response_model=DeadlineCreatedResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_deadline(
    work_item_id: UUID,
    body: CreateDeadlineRequest,
    request: Request,
    response: Response,
    actor_id: Annotated[str, Depends(get_actor_id)],
    idempotency_key: Annotated[str, Depends(get_idempotency_key)],
    uow_factory: Annotated[SqlAlchemyUnitOfWorkFactory, Depends(get_uow_factory)],
) -> DeadlineCreatedResponse:
    result = await CreateDeadlineHandler(uow_factory).execute(
        CreateDeadlineCommand(
            actor_id=actor_id,
            correlation_id=get_correlation_id(request),
            idempotency_key=idempotency_key,
            work_item_id=work_item_id,
            deadline_type=body.deadline_type,
            source=body.source,
            due_at=body.due_at,
            timezone=body.timezone,
            is_hard=body.is_hard,
            source_reference=body.source_reference,
            confidence=body.confidence,
            reminder_policy=body.reminder_policy,
        )
    )
    if result.idempotent_replay:
        response.status_code = status.HTTP_200_OK
    return DeadlineCreatedResponse.model_validate(result)


@router.get("/{work_item_id}/deadlines", response_model=list[DeadlineResponse])
async def list_deadlines(
    work_item_id: UUID,
    uow_factory: Annotated[SqlAlchemyUnitOfWorkFactory, Depends(get_uow_factory)],
) -> list[DeadlineResponse]:
    values = await WorkItemQueryService(uow_factory).list_deadlines(work_item_id)
    return [DeadlineResponse.model_validate(value) for value in values]


@router.post(
    "/{work_item_id}/dependencies",
    response_model=DependencyCreatedResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_dependency(
    work_item_id: UUID,
    body: CreateDependencyRequest,
    request: Request,
    response: Response,
    actor_id: Annotated[str, Depends(get_actor_id)],
    idempotency_key: Annotated[str, Depends(get_idempotency_key)],
    uow_factory: Annotated[SqlAlchemyUnitOfWorkFactory, Depends(get_uow_factory)],
) -> DependencyCreatedResponse:
    result = await CreateDependencyHandler(uow_factory).execute(
        CreateDependencyCommand(
            work_item_id=work_item_id,
            actor_id=actor_id,
            correlation_id=get_correlation_id(request),
            idempotency_key=idempotency_key,
            dependency_type=body.dependency_type,
            depends_on_work_item_id=body.depends_on_work_item_id,
            external_party_id=body.external_party_id,
            description=body.description,
        )
    )
    if result.idempotent_replay:
        response.status_code = status.HTTP_200_OK
    return DependencyCreatedResponse.model_validate(result)


@router.get("/{work_item_id}/dependencies", response_model=list[DependencyResponse])
async def list_dependencies(
    work_item_id: UUID,
    uow_factory: Annotated[SqlAlchemyUnitOfWorkFactory, Depends(get_uow_factory)],
) -> list[DependencyResponse]:
    values = await WorkItemQueryService(uow_factory).list_dependencies(work_item_id)
    return [DependencyResponse.model_validate(value) for value in values]
