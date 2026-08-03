from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, status

from legal_workbench.api.dependencies import (
    get_actor_id,
    get_correlation_id,
    get_idempotency_key,
    get_if_match_version,
    get_uow_factory,
)
from legal_workbench.api.schemas.matters import WorkItemResponse
from legal_workbench.api.schemas.workflow import (
    ChangeWorkItemDeadlineRequest,
    ChangeWorkItemNextActionRequest,
    ChangeWorkItemOwnerRequest,
    ConfirmPriorityRequest,
    CreateDeadlineRequest,
    CreateDependencyRequest,
    DeadlineCreatedResponse,
    DeadlineResponse,
    DependencyCreatedResponse,
    DependencyResolvedResponse,
    DependencyResponse,
    PriorityConfirmationResponse,
    PriorityConfirmedResponse,
    ResolveDependencyRequest,
    WorkItemActionRequest,
    WorkItemActionResponse,
)
from legal_workbench.application.commands import (
    ConfirmPriorityCommand,
    CreateDeadlineCommand,
    CreateDependencyCommand,
)
from legal_workbench.application.queries import WorkItemQueryService
from legal_workbench.application.work_item_lifecycle import (
    ResolveDependencyCommand,
    ResolveDependencyHandler,
    WorkItemActionCommand,
    WorkItemLifecycleHandler,
)
from legal_workbench.application.workflow_handlers import (
    ConfirmPriorityHandler,
    CreateDeadlineHandler,
    CreateDependencyHandler,
)
from legal_workbench.domain.enums import WorkItemAction
from legal_workbench.infrastructure.unit_of_work import SqlAlchemyUnitOfWorkFactory

router = APIRouter(prefix="/work-items", tags=["work-items"])


async def _execute_action(
    *,
    work_item_id: UUID,
    action: WorkItemAction,
    expected_version: int,
    body: WorkItemActionRequest,
    request: Request,
    response: Response,
    actor_id: str,
    idempotency_key: str,
    uow_factory: SqlAlchemyUnitOfWorkFactory,
    owner_id: str | None = None,
    deadline: datetime | None = None,
    next_action: str | None = None,
) -> WorkItemActionResponse:
    result = await WorkItemLifecycleHandler(uow_factory).execute(
        WorkItemActionCommand(
            work_item_id=work_item_id,
            action=action,
            expected_version=expected_version,
            actor_id=actor_id,
            correlation_id=get_correlation_id(request),
            idempotency_key=idempotency_key,
            reason=body.reason,
            owner_id=owner_id,
            deadline=deadline,
            next_action=next_action,
            waiting_party_id=body.waiting_party_id,
            blocker_owner_id=body.blocker_owner_id,
        )
    )
    if result.idempotent_replay:
        response.status_code = status.HTTP_200_OK
    return WorkItemActionResponse.model_validate(result)


@router.get("/{work_item_id}", response_model=WorkItemResponse)
async def get_work_item(
    work_item_id: UUID,
    uow_factory: Annotated[SqlAlchemyUnitOfWorkFactory, Depends(get_uow_factory)],
) -> WorkItemResponse:
    item = await WorkItemQueryService(uow_factory).get(work_item_id)
    return WorkItemResponse.model_validate(item)


@router.post("/{work_item_id}/start", response_model=WorkItemActionResponse)
async def start_work_item(
    work_item_id: UUID,
    body: WorkItemActionRequest,
    request: Request,
    response: Response,
    actor_id: Annotated[str, Depends(get_actor_id)],
    idempotency_key: Annotated[str, Depends(get_idempotency_key)],
    expected_version: Annotated[int, Depends(get_if_match_version)],
    uow_factory: Annotated[SqlAlchemyUnitOfWorkFactory, Depends(get_uow_factory)],
) -> WorkItemActionResponse:
    return await _execute_action(
        work_item_id=work_item_id,
        action=WorkItemAction.START,
        expected_version=expected_version,
        body=body,
        request=request,
        response=response,
        actor_id=actor_id,
        idempotency_key=idempotency_key,
        uow_factory=uow_factory,
    )


@router.post("/{work_item_id}/pause", response_model=WorkItemActionResponse)
async def pause_work_item(
    work_item_id: UUID,
    body: WorkItemActionRequest,
    request: Request,
    response: Response,
    actor_id: Annotated[str, Depends(get_actor_id)],
    idempotency_key: Annotated[str, Depends(get_idempotency_key)],
    expected_version: Annotated[int, Depends(get_if_match_version)],
    uow_factory: Annotated[SqlAlchemyUnitOfWorkFactory, Depends(get_uow_factory)],
) -> WorkItemActionResponse:
    return await _execute_action(
        work_item_id=work_item_id,
        action=WorkItemAction.PAUSE,
        expected_version=expected_version,
        body=body,
        request=request,
        response=response,
        actor_id=actor_id,
        idempotency_key=idempotency_key,
        uow_factory=uow_factory,
    )


@router.post("/{work_item_id}/wait", response_model=WorkItemActionResponse)
async def wait_work_item(
    work_item_id: UUID,
    body: WorkItemActionRequest,
    request: Request,
    response: Response,
    actor_id: Annotated[str, Depends(get_actor_id)],
    idempotency_key: Annotated[str, Depends(get_idempotency_key)],
    expected_version: Annotated[int, Depends(get_if_match_version)],
    uow_factory: Annotated[SqlAlchemyUnitOfWorkFactory, Depends(get_uow_factory)],
) -> WorkItemActionResponse:
    return await _execute_action(
        work_item_id=work_item_id,
        action=WorkItemAction.WAIT,
        expected_version=expected_version,
        body=body,
        request=request,
        response=response,
        actor_id=actor_id,
        idempotency_key=idempotency_key,
        uow_factory=uow_factory,
    )


@router.post("/{work_item_id}/block", response_model=WorkItemActionResponse)
async def block_work_item(
    work_item_id: UUID,
    body: WorkItemActionRequest,
    request: Request,
    response: Response,
    actor_id: Annotated[str, Depends(get_actor_id)],
    idempotency_key: Annotated[str, Depends(get_idempotency_key)],
    expected_version: Annotated[int, Depends(get_if_match_version)],
    uow_factory: Annotated[SqlAlchemyUnitOfWorkFactory, Depends(get_uow_factory)],
) -> WorkItemActionResponse:
    return await _execute_action(
        work_item_id=work_item_id,
        action=WorkItemAction.BLOCK,
        expected_version=expected_version,
        body=body,
        request=request,
        response=response,
        actor_id=actor_id,
        idempotency_key=idempotency_key,
        uow_factory=uow_factory,
    )


@router.post("/{work_item_id}/resume", response_model=WorkItemActionResponse)
async def resume_work_item(
    work_item_id: UUID,
    body: WorkItemActionRequest,
    request: Request,
    response: Response,
    actor_id: Annotated[str, Depends(get_actor_id)],
    idempotency_key: Annotated[str, Depends(get_idempotency_key)],
    expected_version: Annotated[int, Depends(get_if_match_version)],
    uow_factory: Annotated[SqlAlchemyUnitOfWorkFactory, Depends(get_uow_factory)],
) -> WorkItemActionResponse:
    return await _execute_action(
        work_item_id=work_item_id,
        action=WorkItemAction.RESUME,
        expected_version=expected_version,
        body=body,
        request=request,
        response=response,
        actor_id=actor_id,
        idempotency_key=idempotency_key,
        uow_factory=uow_factory,
    )


@router.post("/{work_item_id}/complete", response_model=WorkItemActionResponse)
async def complete_work_item(
    work_item_id: UUID,
    body: WorkItemActionRequest,
    request: Request,
    response: Response,
    actor_id: Annotated[str, Depends(get_actor_id)],
    idempotency_key: Annotated[str, Depends(get_idempotency_key)],
    expected_version: Annotated[int, Depends(get_if_match_version)],
    uow_factory: Annotated[SqlAlchemyUnitOfWorkFactory, Depends(get_uow_factory)],
) -> WorkItemActionResponse:
    return await _execute_action(
        work_item_id=work_item_id,
        action=WorkItemAction.COMPLETE,
        expected_version=expected_version,
        body=body,
        request=request,
        response=response,
        actor_id=actor_id,
        idempotency_key=idempotency_key,
        uow_factory=uow_factory,
    )


@router.post("/{work_item_id}/cancel", response_model=WorkItemActionResponse)
async def cancel_work_item(
    work_item_id: UUID,
    body: WorkItemActionRequest,
    request: Request,
    response: Response,
    actor_id: Annotated[str, Depends(get_actor_id)],
    idempotency_key: Annotated[str, Depends(get_idempotency_key)],
    expected_version: Annotated[int, Depends(get_if_match_version)],
    uow_factory: Annotated[SqlAlchemyUnitOfWorkFactory, Depends(get_uow_factory)],
) -> WorkItemActionResponse:
    return await _execute_action(
        work_item_id=work_item_id,
        action=WorkItemAction.CANCEL,
        expected_version=expected_version,
        body=body,
        request=request,
        response=response,
        actor_id=actor_id,
        idempotency_key=idempotency_key,
        uow_factory=uow_factory,
    )


@router.post("/{work_item_id}/reopen", response_model=WorkItemActionResponse)
async def reopen_work_item(
    work_item_id: UUID,
    body: WorkItemActionRequest,
    request: Request,
    response: Response,
    actor_id: Annotated[str, Depends(get_actor_id)],
    idempotency_key: Annotated[str, Depends(get_idempotency_key)],
    expected_version: Annotated[int, Depends(get_if_match_version)],
    uow_factory: Annotated[SqlAlchemyUnitOfWorkFactory, Depends(get_uow_factory)],
) -> WorkItemActionResponse:
    return await _execute_action(
        work_item_id=work_item_id,
        action=WorkItemAction.REOPEN,
        expected_version=expected_version,
        body=body,
        request=request,
        response=response,
        actor_id=actor_id,
        idempotency_key=idempotency_key,
        uow_factory=uow_factory,
    )


@router.patch("/{work_item_id}/owner", response_model=WorkItemActionResponse)
async def change_work_item_owner(
    work_item_id: UUID,
    body: ChangeWorkItemOwnerRequest,
    request: Request,
    response: Response,
    actor_id: Annotated[str, Depends(get_actor_id)],
    idempotency_key: Annotated[str, Depends(get_idempotency_key)],
    expected_version: Annotated[int, Depends(get_if_match_version)],
    uow_factory: Annotated[SqlAlchemyUnitOfWorkFactory, Depends(get_uow_factory)],
) -> WorkItemActionResponse:
    return await _execute_action(
        work_item_id=work_item_id,
        action=WorkItemAction.CHANGE_OWNER,
        expected_version=expected_version,
        body=WorkItemActionRequest(reason=body.reason),
        request=request,
        response=response,
        actor_id=actor_id,
        idempotency_key=idempotency_key,
        uow_factory=uow_factory,
        owner_id=body.owner_id,
    )


@router.patch("/{work_item_id}/deadline", response_model=WorkItemActionResponse)
async def change_work_item_deadline(
    work_item_id: UUID,
    body: ChangeWorkItemDeadlineRequest,
    request: Request,
    response: Response,
    actor_id: Annotated[str, Depends(get_actor_id)],
    idempotency_key: Annotated[str, Depends(get_idempotency_key)],
    expected_version: Annotated[int, Depends(get_if_match_version)],
    uow_factory: Annotated[SqlAlchemyUnitOfWorkFactory, Depends(get_uow_factory)],
) -> WorkItemActionResponse:
    return await _execute_action(
        work_item_id=work_item_id,
        action=WorkItemAction.CHANGE_DEADLINE,
        expected_version=expected_version,
        body=WorkItemActionRequest(reason=body.reason),
        request=request,
        response=response,
        actor_id=actor_id,
        idempotency_key=idempotency_key,
        uow_factory=uow_factory,
        deadline=body.deadline,
    )


@router.patch("/{work_item_id}/next-action", response_model=WorkItemActionResponse)
async def change_work_item_next_action(
    work_item_id: UUID,
    body: ChangeWorkItemNextActionRequest,
    request: Request,
    response: Response,
    actor_id: Annotated[str, Depends(get_actor_id)],
    idempotency_key: Annotated[str, Depends(get_idempotency_key)],
    expected_version: Annotated[int, Depends(get_if_match_version)],
    uow_factory: Annotated[SqlAlchemyUnitOfWorkFactory, Depends(get_uow_factory)],
) -> WorkItemActionResponse:
    return await _execute_action(
        work_item_id=work_item_id,
        action=WorkItemAction.CHANGE_NEXT_ACTION,
        expected_version=expected_version,
        body=WorkItemActionRequest(reason=body.reason),
        request=request,
        response=response,
        actor_id=actor_id,
        idempotency_key=idempotency_key,
        uow_factory=uow_factory,
        next_action=body.next_action,
    )


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
    expected_version: Annotated[int, Depends(get_if_match_version)],
    uow_factory: Annotated[SqlAlchemyUnitOfWorkFactory, Depends(get_uow_factory)],
) -> DependencyCreatedResponse:
    result = await CreateDependencyHandler(uow_factory).execute(
        CreateDependencyCommand(
            work_item_id=work_item_id,
            work_item_version=expected_version,
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


@router.post(
    "/{work_item_id}/dependencies/{dependency_id}/resolve",
    response_model=DependencyResolvedResponse,
)
async def resolve_dependency(
    work_item_id: UUID,
    dependency_id: UUID,
    body: ResolveDependencyRequest,
    request: Request,
    response: Response,
    actor_id: Annotated[str, Depends(get_actor_id)],
    idempotency_key: Annotated[str, Depends(get_idempotency_key)],
    expected_version: Annotated[int, Depends(get_if_match_version)],
    uow_factory: Annotated[SqlAlchemyUnitOfWorkFactory, Depends(get_uow_factory)],
) -> DependencyResolvedResponse:
    result = await ResolveDependencyHandler(uow_factory).execute(
        ResolveDependencyCommand(
            work_item_id=work_item_id,
            dependency_id=dependency_id,
            work_item_version=expected_version,
            dependency_version=body.dependency_version,
            actor_id=actor_id,
            correlation_id=get_correlation_id(request),
            idempotency_key=idempotency_key,
            reason=body.reason,
        )
    )
    if result.idempotent_replay:
        response.status_code = status.HTTP_200_OK
    return DependencyResolvedResponse.model_validate(result)


@router.get("/{work_item_id}/dependencies", response_model=list[DependencyResponse])
async def list_dependencies(
    work_item_id: UUID,
    uow_factory: Annotated[SqlAlchemyUnitOfWorkFactory, Depends(get_uow_factory)],
) -> list[DependencyResponse]:
    values = await WorkItemQueryService(uow_factory).list_dependencies(work_item_id)
    return [DependencyResponse.model_validate(value) for value in values]
