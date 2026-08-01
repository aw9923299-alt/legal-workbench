from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status

from legal_workbench.api.dependencies import (
    get_actor_id,
    get_correlation_id,
    get_idempotency_key,
    get_uow_factory,
)
from legal_workbench.api.schemas.candidates import (
    CandidateCreatedResponse,
    CandidateResponse,
    ConfirmCreateMatterRequest,
    CreateCandidateRequest,
    MatterCreatedResponse,
)
from legal_workbench.application.commands import (
    ConfirmCandidateCreateMatterCommand,
    CreateCandidateCommand,
    InitialWorkItemInput,
)
from legal_workbench.application.handlers import (
    ConfirmCandidateCreateMatterHandler,
    CreateCandidateHandler,
)
from legal_workbench.application.queries import CandidateQueryService
from legal_workbench.domain.enums import CandidateStatus
from legal_workbench.infrastructure.unit_of_work import SqlAlchemyUnitOfWorkFactory

router = APIRouter(prefix="/inbox/candidates", tags=["message-candidates"])


@router.post("", response_model=CandidateCreatedResponse, status_code=status.HTTP_201_CREATED)
async def create_candidate(
    body: CreateCandidateRequest,
    request: Request,
    response: Response,
    actor_id: Annotated[str, Depends(get_actor_id)],
    idempotency_key: Annotated[str, Depends(get_idempotency_key)],
    uow_factory: Annotated[SqlAlchemyUnitOfWorkFactory, Depends(get_uow_factory)],
) -> CandidateCreatedResponse:
    result = await CreateCandidateHandler(uow_factory).execute(
        CreateCandidateCommand(
            source_type=body.context.source_type,
            source_ids=body.context.source_ids,
            message_ids=body.context.message_ids,
            file_ids=body.context.file_ids,
            relevant_matter_ids=body.context.relevant_matter_ids,
            participant_ids=body.context.participant_ids,
            permission_snapshot=body.context.permission_snapshot,
            generated_at=body.context.generated_at,
            content_hash=body.context.content_hash,
            actor_id=actor_id,
            correlation_id=get_correlation_id(request),
            idempotency_key=idempotency_key,
            status=body.status,
            legal_relevance=body.legal_relevance,
            message_role=body.message_role,
            recommended_action=body.recommended_action,
            confidence=body.confidence,
            title_proposal=body.title_proposal,
            category_proposals=body.category_proposals,
            deadline_proposals=body.deadline_proposals,
            related_matter_proposals=body.related_matter_proposals,
            evidence_refs=body.evidence_refs,
            agent_run_id=body.agent_run_id,
        )
    )
    if result.idempotent_replay:
        response.status_code = status.HTTP_200_OK
    return CandidateCreatedResponse(
        candidate_id=result.candidate_id,
        version=result.version,
        idempotent_replay=result.idempotent_replay,
    )


@router.get("", response_model=list[CandidateResponse])
async def list_candidates(
    uow_factory: Annotated[SqlAlchemyUnitOfWorkFactory, Depends(get_uow_factory)],
    candidate_status: Annotated[CandidateStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[CandidateResponse]:
    candidates = await CandidateQueryService(uow_factory).list(
        status=candidate_status, limit=limit
    )
    return [CandidateResponse.model_validate(candidate) for candidate in candidates]


@router.get("/{candidate_id}", response_model=CandidateResponse)
async def get_candidate(
    candidate_id: UUID,
    uow_factory: Annotated[SqlAlchemyUnitOfWorkFactory, Depends(get_uow_factory)],
) -> CandidateResponse:
    candidate = await CandidateQueryService(uow_factory).get(candidate_id)
    return CandidateResponse.model_validate(candidate)


@router.post(
    "/{candidate_id}/confirm-create",
    response_model=MatterCreatedResponse,
    status_code=status.HTTP_201_CREATED,
)
async def confirm_create_matter(
    candidate_id: UUID,
    body: ConfirmCreateMatterRequest,
    request: Request,
    response: Response,
    actor_id: Annotated[str, Depends(get_actor_id)],
    idempotency_key: Annotated[str, Depends(get_idempotency_key)],
    uow_factory: Annotated[SqlAlchemyUnitOfWorkFactory, Depends(get_uow_factory)],
) -> MatterCreatedResponse:
    result = await ConfirmCandidateCreateMatterHandler(uow_factory).execute(
        ConfirmCandidateCreateMatterCommand(
            candidate_id=candidate_id,
            candidate_version=body.candidate_version,
            actor_id=actor_id,
            correlation_id=get_correlation_id(request),
            idempotency_key=idempotency_key,
            title=body.title,
            primary_category=body.primary_category,
            secondary_categories=body.secondary_categories,
            owner_id=body.owner_id,
            requester_ids=body.requester_ids,
            legal_risk=body.legal_risk,
            business_impact=body.business_impact,
            confidentiality=body.confidentiality,
            summary=body.summary,
            objective=body.objective,
            initial_work_items=[
                InitialWorkItemInput(
                    title=item.title,
                    owner_id=item.owner_id,
                    priority=item.priority,
                    priority_source=item.priority_source,
                    next_action=item.next_action,
                    priority_reasons=item.priority_reasons,
                    ai_suggested_priority=item.ai_suggested_priority,
                    estimated_minutes=item.estimated_minutes,
                    planned_complete_at=item.planned_complete_at,
                )
                for item in body.initial_work_items
            ],
        )
    )
    if result.idempotent_replay:
        response.status_code = status.HTTP_200_OK
    return MatterCreatedResponse(
        matter_id=result.matter_id,
        matter_number=result.matter_number,
        work_item_ids=result.work_item_ids,
        idempotent_replay=result.idempotent_replay,
    )
