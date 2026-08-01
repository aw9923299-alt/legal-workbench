from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status

from legal_workbench.api.dependencies import (
    get_actor_id,
    get_correlation_id,
    get_idempotency_key,
    get_uow_factory,
)
from legal_workbench.api.schemas.reviews import (
    CommunicationResponse,
    CreateReviewPackageRequest,
    QueueCommunicationResponse,
    ReviewPackageCreatedResponse,
    ReviewPackageDecisionRequest,
    ReviewPackageResponse,
    ReviewRecordResponse,
    ReviewRecordedResponse,
    SubmitReviewPackageRequest,
)
from legal_workbench.application.commands import (
    CreateReviewPackageCommand,
    QueueCommunicationCommand,
    ReviewPackageCommand,
    SubmitReviewPackageCommand,
)
from legal_workbench.application.queries import ReviewQueryService
from legal_workbench.application.review_handlers import (
    CreateReviewPackageHandler,
    QueueCommunicationHandler,
    ReviewPackageHandler,
    SubmitReviewPackageHandler,
)
from legal_workbench.domain.enums import CommunicationStatus, ReviewPackageStatus
from legal_workbench.infrastructure.unit_of_work import SqlAlchemyUnitOfWorkFactory

router = APIRouter(prefix="/reviews", tags=["reviews"])


@router.post(
    "/packages",
    response_model=ReviewPackageCreatedResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_review_package(
    body: CreateReviewPackageRequest,
    request: Request,
    response: Response,
    actor_id: Annotated[str, Depends(get_actor_id)],
    idempotency_key: Annotated[str, Depends(get_idempotency_key)],
    uow_factory: Annotated[SqlAlchemyUnitOfWorkFactory, Depends(get_uow_factory)],
) -> ReviewPackageCreatedResponse:
    result = await CreateReviewPackageHandler(uow_factory).execute(
        CreateReviewPackageCommand(
            matter_id=body.matter_id,
            work_item_id=body.work_item_id,
            actor_id=actor_id,
            correlation_id=get_correlation_id(request),
            idempotency_key=idempotency_key,
            package_type=body.package_type,
            title=body.title,
            background=body.background,
            confirmed_facts=body.confirmed_facts,
            unconfirmed_facts=body.unconfirmed_facts,
            reasoning=body.reasoning,
            risks=body.risks,
            alternatives=body.alternatives,
            citations=body.citations,
            proposed_content=body.proposed_content,
            target=body.target,
            submit_for_review=body.submit_for_review,
        )
    )
    if result.idempotent_replay:
        response.status_code = status.HTTP_200_OK
    return ReviewPackageCreatedResponse.model_validate(result)


@router.get("/packages", response_model=list[ReviewPackageResponse])
async def list_review_packages(
    uow_factory: Annotated[SqlAlchemyUnitOfWorkFactory, Depends(get_uow_factory)],
    package_status: Annotated[ReviewPackageStatus | None, Query(alias="status")] = None,
    matter_id: Annotated[UUID | None, Query(alias="matterId")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[ReviewPackageResponse]:
    values = await ReviewQueryService(uow_factory).list_packages(
        status=package_status, matter_id=matter_id, limit=limit
    )
    return [ReviewPackageResponse.model_validate(value) for value in values]


@router.get("/packages/{package_id}", response_model=ReviewPackageResponse)
async def get_review_package(
    package_id: UUID,
    uow_factory: Annotated[SqlAlchemyUnitOfWorkFactory, Depends(get_uow_factory)],
) -> ReviewPackageResponse:
    value = await ReviewQueryService(uow_factory).get_package(package_id)
    return ReviewPackageResponse.model_validate(value)


@router.post("/packages/{package_id}/submit", response_model=ReviewPackageCreatedResponse)
async def submit_review_package(
    package_id: UUID,
    body: SubmitReviewPackageRequest,
    request: Request,
    response: Response,
    actor_id: Annotated[str, Depends(get_actor_id)],
    idempotency_key: Annotated[str, Depends(get_idempotency_key)],
    uow_factory: Annotated[SqlAlchemyUnitOfWorkFactory, Depends(get_uow_factory)],
) -> ReviewPackageCreatedResponse:
    result = await SubmitReviewPackageHandler(uow_factory).execute(
        SubmitReviewPackageCommand(
            review_package_id=package_id,
            package_version=body.package_version,
            actor_id=actor_id,
            correlation_id=get_correlation_id(request),
            idempotency_key=idempotency_key,
        )
    )
    if result.idempotent_replay:
        response.status_code = status.HTTP_200_OK
    return ReviewPackageCreatedResponse.model_validate(result)


@router.post("/packages/{package_id}/records", response_model=ReviewRecordedResponse)
async def review_package(
    package_id: UUID,
    body: ReviewPackageDecisionRequest,
    request: Request,
    response: Response,
    actor_id: Annotated[str, Depends(get_actor_id)],
    idempotency_key: Annotated[str, Depends(get_idempotency_key)],
    uow_factory: Annotated[SqlAlchemyUnitOfWorkFactory, Depends(get_uow_factory)],
) -> ReviewRecordedResponse:
    result = await ReviewPackageHandler(uow_factory).execute(
        ReviewPackageCommand(
            review_package_id=package_id,
            package_version=body.package_version,
            actor_id=actor_id,
            correlation_id=get_correlation_id(request),
            idempotency_key=idempotency_key,
            decision=body.decision,
            comments=body.comments,
            final_content=body.final_content,
            change_summary=body.change_summary,
            reusable_as_example=body.reusable_as_example,
        )
    )
    if result.idempotent_replay:
        response.status_code = status.HTTP_200_OK
    return ReviewRecordedResponse.model_validate(result)


@router.get("/packages/{package_id}/records", response_model=list[ReviewRecordResponse])
async def list_review_records(
    package_id: UUID,
    uow_factory: Annotated[SqlAlchemyUnitOfWorkFactory, Depends(get_uow_factory)],
) -> list[ReviewRecordResponse]:
    values = await ReviewQueryService(uow_factory).list_records(package_id)
    return [ReviewRecordResponse.model_validate(value) for value in values]


@router.post("/packages/{package_id}/communications", response_model=QueueCommunicationResponse)
async def queue_communication(
    package_id: UUID,
    request: Request,
    response: Response,
    actor_id: Annotated[str, Depends(get_actor_id)],
    idempotency_key: Annotated[str, Depends(get_idempotency_key)],
    uow_factory: Annotated[SqlAlchemyUnitOfWorkFactory, Depends(get_uow_factory)],
) -> QueueCommunicationResponse:
    result = await QueueCommunicationHandler(uow_factory).execute(
        QueueCommunicationCommand(
            review_package_id=package_id,
            actor_id=actor_id,
            correlation_id=get_correlation_id(request),
            idempotency_key=idempotency_key,
        )
    )
    if result.idempotent_replay:
        response.status_code = status.HTTP_200_OK
    return QueueCommunicationResponse.model_validate(result)


@router.get("/communications", response_model=list[CommunicationResponse])
async def list_communications(
    uow_factory: Annotated[SqlAlchemyUnitOfWorkFactory, Depends(get_uow_factory)],
    communication_status: Annotated[
        CommunicationStatus | None, Query(alias="status")
    ] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[CommunicationResponse]:
    values = await ReviewQueryService(uow_factory).list_communications(
        status=communication_status, limit=limit
    )
    return [CommunicationResponse.model_validate(value) for value in values]
