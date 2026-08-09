from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request

from legal_workbench.api.dependencies import (
    get_actor_id,
    get_correlation_id,
    get_idempotency_key,
    get_if_match_version,
    get_uow_factory,
)
from legal_workbench.api.schemas.knowledge import (
    KnowledgeChunkResponse,
    KnowledgeDocumentDetailsResponse,
    KnowledgeDocumentResponse,
    KnowledgeMetadataUpdatedResponse,
    KnowledgeRetrievalLogResponse,
    UpdateKnowledgeMetadataRequest,
)
from legal_workbench.application.knowledge import (
    KnowledgeManagementService,
    KnowledgeMetadataUpdate,
)
from legal_workbench.domain.enums import AuthorityType, KnowledgeMetadataStatus
from legal_workbench.infrastructure.unit_of_work import SqlAlchemyUnitOfWorkFactory

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


@router.get("/documents", response_model=list[KnowledgeDocumentResponse])
async def list_knowledge_documents(
    uow_factory: Annotated[SqlAlchemyUnitOfWorkFactory, Depends(get_uow_factory)],
    authority_type: Annotated[AuthorityType | None, Query(alias="authorityType")] = None,
    metadata_status: Annotated[
        KnowledgeMetadataStatus | None, Query(alias="metadataStatus")
    ] = None,
    enabled: Annotated[bool | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> list[KnowledgeDocumentResponse]:
    values = await KnowledgeManagementService(uow_factory).list_documents(
        authority_type=authority_type,
        metadata_status=metadata_status,
        enabled=enabled,
        limit=limit,
    )
    return [KnowledgeDocumentResponse.model_validate(value) for value in values]


@router.get(
    "/documents/{document_id}",
    response_model=KnowledgeDocumentDetailsResponse,
)
async def get_knowledge_document(
    document_id: UUID,
    uow_factory: Annotated[SqlAlchemyUnitOfWorkFactory, Depends(get_uow_factory)],
) -> KnowledgeDocumentDetailsResponse:
    details = await KnowledgeManagementService(uow_factory).get_document(document_id)
    return KnowledgeDocumentDetailsResponse(
        document=KnowledgeDocumentResponse.model_validate(details.document),
        chunks=[KnowledgeChunkResponse.model_validate(value) for value in details.chunks],
        retrieval_logs=[
            KnowledgeRetrievalLogResponse.model_validate(value)
            for value in details.retrieval_logs
        ],
    )


@router.patch(
    "/documents/{document_id}/metadata",
    response_model=KnowledgeMetadataUpdatedResponse,
)
async def update_knowledge_metadata(
    document_id: UUID,
    body: UpdateKnowledgeMetadataRequest,
    request: Request,
    actor_id: Annotated[str, Depends(get_actor_id)],
    expected_version: Annotated[int, Depends(get_if_match_version)],
    idempotency_key: Annotated[str, Depends(get_idempotency_key)],
    uow_factory: Annotated[SqlAlchemyUnitOfWorkFactory, Depends(get_uow_factory)],
) -> KnowledgeMetadataUpdatedResponse:
    result = await KnowledgeManagementService(uow_factory).update_metadata(
        document_id=document_id,
        expected_version=expected_version,
        update=KnowledgeMetadataUpdate(
            title=body.title,
            authority_type=body.authority_type,
            authority_role=body.authority_role,
            authority_status=body.authority_status,
            jurisdiction=body.jurisdiction,
            effective_from=body.effective_from,
            effective_to=body.effective_to,
            issuer=body.issuer,
            document_number=body.document_number,
            enabled=body.enabled,
        ),
        actor_id=actor_id,
        correlation_id=get_correlation_id(request),
        idempotency_key=idempotency_key,
    )
    return KnowledgeMetadataUpdatedResponse.model_validate(result)
