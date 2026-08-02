from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from legal_workbench.api.dependencies import get_uow_factory
from legal_workbench.api.schemas.feishu import (
    CandidateRevisionResponse,
    FeishuAttachmentResponse,
    FeishuMessageDetailResponse,
    FeishuMessageSummaryResponse,
    FeishuMessageVersionResponse,
)
from legal_workbench.application.queries import (
    FeishuInboxQueryService,
    FeishuMessageDetails,
)
from legal_workbench.domain.entities import FeishuMessage
from legal_workbench.domain.enums import FeishuMessageStatus
from legal_workbench.infrastructure.unit_of_work import SqlAlchemyUnitOfWorkFactory

router = APIRouter(prefix="/feishu/messages", tags=["feishu-messages"])


def _proposal_value(values: list[dict[str, object]], key: str) -> str | None:
    for value in values:
        selected = value.get(key)
        if isinstance(selected, str):
            return selected
    return None


def _summary(
    message: FeishuMessage,
    *,
    run: object | None = None,
    candidate: object | None = None,
) -> FeishuMessageSummaryResponse:
    from legal_workbench.domain.entities import AgentRun, MessageCandidate

    typed_run = run if isinstance(run, AgentRun) else None
    typed_candidate = candidate if isinstance(candidate, MessageCandidate) else None
    return FeishuMessageSummaryResponse(
        id=message.id,
        message_id=message.message_id,
        tenant_key=message.tenant_key,
        chat_id=message.chat_id,
        thread_id=message.thread_id,
        parent_message_id=message.parent_id,
        root_message_id=message.root_id,
        sender_id=message.sender_id,
        sender_type=message.sender_type,
        message_type=message.message_type,
        plain_text=message.plain_text,
        sent_at=message.create_time,
        edited_at=message.edited_at,
        recalled_at=message.recalled_at,
        status=message.status,
        unsupported_reason=message.unsupported_reason,
        analysis_attempts=message.analysis_attempts,
        failure_code=message.failure_code,
        failure_message=message.failure_message,
        agent_run_id=typed_run.id if typed_run else None,
        agent_status=typed_run.status if typed_run else None,
        candidate_id=typed_candidate.id if typed_candidate else None,
        candidate_status=typed_candidate.status if typed_candidate else None,
        confidence=typed_candidate.confidence if typed_candidate else None,
        suggested_category=(
            _proposal_value(typed_candidate.category_proposals, "category")
            if typed_candidate
            else None
        ),
        suggested_deadline=(
            _proposal_value(typed_candidate.deadline_proposals, "resolvedAt")
            or _proposal_value(typed_candidate.deadline_proposals, "rawText")
            if typed_candidate
            else None
        ),
    )


@router.get("", response_model=list[FeishuMessageSummaryResponse])
async def list_feishu_messages(
    uow_factory: Annotated[SqlAlchemyUnitOfWorkFactory, Depends(get_uow_factory)],
    statuses: Annotated[list[FeishuMessageStatus] | None, Query(alias="status")] = None,
    search: Annotated[str | None, Query(max_length=200)] = None,
    category: Annotated[str | None, Query(max_length=80)] = None,
    chat_id: Annotated[str | None, Query(alias="chatId", max_length=200)] = None,
    created_from: Annotated[datetime | None, Query(alias="from")] = None,
    created_to: Annotated[datetime | None, Query(alias="to")] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[FeishuMessageSummaryResponse]:
    values = await FeishuInboxQueryService(uow_factory).list(
        statuses=statuses,
        search=search,
        chat_id=chat_id,
        created_from=created_from,
        created_to=created_to,
        limit=limit,
    )
    if category:
        values = [
            value
            for value in values
            if value.candidate
            and _proposal_value(value.candidate.category_proposals, "category") == category
        ]
    return [
        _summary(value.message, run=value.run, candidate=value.candidate) for value in values
    ]


@router.get("/{message_id}", response_model=FeishuMessageDetailResponse)
async def get_feishu_message(
    message_id: UUID,
    uow_factory: Annotated[SqlAlchemyUnitOfWorkFactory, Depends(get_uow_factory)],
) -> FeishuMessageDetailResponse:
    details: FeishuMessageDetails = await FeishuInboxQueryService(uow_factory).get(
        message_id
    )
    summary = _summary(details.message, run=details.run, candidate=details.candidate)
    return FeishuMessageDetailResponse(
        **summary.model_dump(),
        structured_content=details.message.structured_content,
        raw_payload=details.message.raw_message,
        context_messages=[_summary(value) for value in details.context_messages],
        versions=[
            FeishuMessageVersionResponse.model_validate(value) for value in details.versions
        ],
        attachments=[
            FeishuAttachmentResponse.model_validate(value) for value in details.attachments
        ],
        candidate_revisions=[
            CandidateRevisionResponse.model_validate(value)
            for value in details.candidate_revisions
        ],
    )
