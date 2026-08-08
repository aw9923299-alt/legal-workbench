from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, status

from legal_workbench.api.dependencies import (
    get_actor_id,
    get_correlation_id,
    get_idempotency_key,
    get_uow_factory,
)
from legal_workbench.api.schemas.matter_updates import (
    MatterUpdateProposalResponse,
    MatterUpdateProposalReviewedResponse,
    ReviewMatterUpdateProposalRequest,
)
from legal_workbench.application.matter_updates import (
    ReviewMatterUpdateProposalCommand,
    ReviewMatterUpdateProposalHandler,
)
from legal_workbench.domain.entities import ProposalFieldDecision
from legal_workbench.domain.errors import EntityNotFoundError
from legal_workbench.infrastructure.unit_of_work import SqlAlchemyUnitOfWorkFactory

router = APIRouter(prefix="/matter-update-proposals", tags=["matter-update-proposals"])


@router.get("/{proposal_id}", response_model=MatterUpdateProposalResponse)
async def get_matter_update_proposal(
    proposal_id: UUID,
    uow_factory: Annotated[SqlAlchemyUnitOfWorkFactory, Depends(get_uow_factory)],
) -> MatterUpdateProposalResponse:
    async with uow_factory() as uow:
        proposal = await uow.matter_update_proposals.get(proposal_id)
        if proposal is None:
            raise EntityNotFoundError(
                "Matter update proposal was not found.",
                details={"proposalId": str(proposal_id)},
            )
        return MatterUpdateProposalResponse.model_validate(proposal)


@router.post("/{proposal_id}/review", response_model=MatterUpdateProposalReviewedResponse)
async def review_matter_update_proposal(
    proposal_id: UUID,
    body: ReviewMatterUpdateProposalRequest,
    request: Request,
    response: Response,
    actor_id: Annotated[str, Depends(get_actor_id)],
    idempotency_key: Annotated[str, Depends(get_idempotency_key)],
    uow_factory: Annotated[SqlAlchemyUnitOfWorkFactory, Depends(get_uow_factory)],
) -> MatterUpdateProposalReviewedResponse:
    result = await ReviewMatterUpdateProposalHandler(uow_factory).execute(
        ReviewMatterUpdateProposalCommand(
            proposal_id=proposal_id,
            proposal_version=body.proposal_version,
            matter_version=body.matter_version,
            decisions=[
                ProposalFieldDecision(
                    field_name=value.field_name,
                    decision=value.decision,
                    final_value=value.final_value,
                )
                for value in body.decisions
            ],
            rejection_reason=body.rejection_reason,
            actor_id=actor_id,
            correlation_id=get_correlation_id(request),
            idempotency_key=idempotency_key,
        )
    )
    if result.idempotent_replay:
        response.status_code = status.HTTP_200_OK
    return MatterUpdateProposalReviewedResponse(
        proposal_id=result.proposal_id,
        matter_id=result.matter_id,
        status=result.status,
        proposal_version=result.proposal_version,
        matter_version=result.matter_version,
        work_item_ids=result.work_item_ids,
        deadline_id=result.deadline_id,
        idempotent_replay=result.idempotent_replay,
    )
