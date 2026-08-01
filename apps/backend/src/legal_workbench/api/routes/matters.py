from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status

from legal_workbench.api.dependencies import (
    get_actor_id,
    get_correlation_id,
    get_idempotency_key,
    get_uow_factory,
)
from legal_workbench.api.schemas.matters import (
    CreateWorkItemRequest,
    LegalMatterResponse,
    WorkItemCreatedResponse,
    WorkItemResponse,
)
from legal_workbench.application.commands import AddWorkItemCommand
from legal_workbench.application.handlers import AddWorkItemHandler
from legal_workbench.application.queries import MatterQueryService
from legal_workbench.infrastructure.unit_of_work import SqlAlchemyUnitOfWorkFactory

router = APIRouter(prefix="/matters", tags=["legal-matters"])


@router.get("", response_model=list[LegalMatterResponse])
async def list_matters(
    uow_factory: Annotated[SqlAlchemyUnitOfWorkFactory, Depends(get_uow_factory)],
    owner_id: Annotated[str | None, Query(alias="ownerId")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[LegalMatterResponse]:
    matters = await MatterQueryService(uow_factory).list(owner_id=owner_id, limit=limit)
    return [LegalMatterResponse.model_validate(matter) for matter in matters]


@router.get("/{matter_id}", response_model=LegalMatterResponse)
async def get_matter(
    matter_id: UUID,
    uow_factory: Annotated[SqlAlchemyUnitOfWorkFactory, Depends(get_uow_factory)],
) -> LegalMatterResponse:
    matter = await MatterQueryService(uow_factory).get(matter_id)
    return LegalMatterResponse.model_validate(matter)


@router.get("/{matter_id}/work-items", response_model=list[WorkItemResponse])
async def list_work_items(
    matter_id: UUID,
    uow_factory: Annotated[SqlAlchemyUnitOfWorkFactory, Depends(get_uow_factory)],
) -> list[WorkItemResponse]:
    work_items = await MatterQueryService(uow_factory).list_work_items(matter_id)
    return [WorkItemResponse.model_validate(item) for item in work_items]


@router.post(
    "/{matter_id}/work-items",
    response_model=WorkItemCreatedResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_work_item(
    matter_id: UUID,
    body: CreateWorkItemRequest,
    request: Request,
    response: Response,
    actor_id: Annotated[str, Depends(get_actor_id)],
    idempotency_key: Annotated[str, Depends(get_idempotency_key)],
    uow_factory: Annotated[SqlAlchemyUnitOfWorkFactory, Depends(get_uow_factory)],
) -> WorkItemCreatedResponse:
    result = await AddWorkItemHandler(uow_factory).execute(
        AddWorkItemCommand(
            matter_id=matter_id,
            actor_id=actor_id,
            correlation_id=get_correlation_id(request),
            idempotency_key=idempotency_key,
            title=body.title,
            owner_id=body.owner_id,
            priority=body.priority,
            priority_source=body.priority_source,
            next_action=body.next_action,
            priority_reasons=body.priority_reasons,
            ai_suggested_priority=body.ai_suggested_priority,
            estimated_minutes=body.estimated_minutes,
            planned_complete_at=body.planned_complete_at,
        )
    )
    if result.idempotent_replay:
        response.status_code = status.HTTP_200_OK
    return WorkItemCreatedResponse(
        work_item_id=result.work_item_id,
        matter_id=result.matter_id,
        idempotent_replay=result.idempotent_replay,
    )
