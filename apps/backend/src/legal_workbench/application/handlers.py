from __future__ import annotations

import hashlib
import json
from uuid import UUID, uuid4

from legal_workbench.application.commands import (
    AddWorkItemCommand,
    ConfirmCandidateCreateMatterCommand,
    CreateCandidateCommand,
    ResolveCandidateCommand,
)
from legal_workbench.application.ports import UnitOfWorkFactory
from legal_workbench.application.results import (
    CandidateCreatedResult,
    CandidateResolvedResult,
    MatterCreatedResult,
    WorkItemCreatedResult,
)
from legal_workbench.domain.entities import (
    AuditEvent,
    ContextSnapshot,
    IdempotencyRecord,
    LegalMatter,
    MessageCandidate,
    OutboxEvent,
    WorkItem,
)
from legal_workbench.domain.enums import (
    CandidateMatterRelation,
    CandidateResolutionAction,
    CandidateStatus,
)
from legal_workbench.domain.errors import (
    DomainValidationError,
    EntityNotFoundError,
    IdempotencyConflictError,
)


def _request_hash(payload: dict[str, object]) -> str:
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _legal_butler_requested_event(
    *,
    candidate: MessageCandidate,
    matter: LegalMatter,
    work_item_id: UUID | None,
    actor_id: str,
    correlation_id: str,
) -> OutboxEvent:
    return OutboxEvent(
        id=uuid4(),
        event_type="LegalButlerRequested",
        aggregate_type="legal_matter",
        aggregate_id=matter.id,
        payload={
            "matterId": str(matter.id),
            "workItemId": str(work_item_id) if work_item_id else None,
            "contextSnapshotId": str(candidate.context_snapshot_id),
            "objective": matter.objective or matter.title,
            "actorId": actor_id,
            "idempotencyKey": f"candidate:{candidate.id}:matter:{matter.id}",
            "triggerSource": "candidate_confirmed",
            "specialRequirements": None,
            "specialistOnly": None,
            "jurisdiction": "CN",
        },
        correlation_id=correlation_id,
    )


def _candidate_result_from_replay(record: IdempotencyRecord) -> CandidateCreatedResult:
    return CandidateCreatedResult(
        candidate_id=UUID(str(record.response_payload["candidateId"])),
        version=int(str(record.response_payload["version"])),
        idempotent_replay=True,
    )


def _matter_result_from_replay(record: IdempotencyRecord) -> MatterCreatedResult:
    work_item_ids_value = record.response_payload.get("workItemIds", [])
    if not isinstance(work_item_ids_value, list):
        raise RuntimeError("Invalid idempotency response payload for matter creation")
    return MatterCreatedResult(
        matter_id=UUID(str(record.response_payload["matterId"])),
        matter_number=str(record.response_payload["matterNumber"]),
        work_item_ids=[UUID(str(item)) for item in work_item_ids_value],
        idempotent_replay=True,
    )


def _resolved_result_from_replay(record: IdempotencyRecord) -> CandidateResolvedResult:
    matter_id = record.response_payload.get("matterId")
    return CandidateResolvedResult(
        candidate_id=UUID(str(record.response_payload["candidateId"])),
        status=CandidateStatus(str(record.response_payload["status"])),
        matter_id=UUID(str(matter_id)) if matter_id else None,
        version=int(str(record.response_payload["version"])),
        idempotent_replay=True,
    )


def _work_item_result_from_replay(record: IdempotencyRecord) -> WorkItemCreatedResult:
    return WorkItemCreatedResult(
        work_item_id=UUID(str(record.response_payload["workItemId"])),
        matter_id=UUID(str(record.response_payload["matterId"])),
        idempotent_replay=True,
    )


class CreateCandidateHandler:
    OPERATION = "create_message_candidate"

    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def execute(self, command: CreateCandidateCommand) -> CandidateCreatedResult:
        request_payload: dict[str, object] = {
            "sourceType": command.source_type,
            "sourceIds": command.source_ids,
            "messageIds": command.message_ids,
            "fileIds": command.file_ids,
            "relevantMatterIds": command.relevant_matter_ids,
            "participantIds": command.participant_ids,
            "permissionSnapshot": command.permission_snapshot,
            "generatedAt": command.generated_at,
            "contentHash": command.content_hash,
            "status": command.status.value,
            "legalRelevance": command.legal_relevance.value,
            "messageRole": command.message_role.value,
            "recommendedAction": command.recommended_action.value,
            "confidence": command.confidence,
            "titleProposal": command.title_proposal,
            "categoryProposals": command.category_proposals,
            "deadlineProposals": command.deadline_proposals,
            "relatedMatterProposals": command.related_matter_proposals,
            "evidenceRefs": command.evidence_refs,
            "agentRunId": command.agent_run_id,
        }
        request_hash = _request_hash(request_payload)

        async with self._uow_factory() as uow:
            await uow.lock_idempotency(
                operation=self.OPERATION, key=command.idempotency_key
            )
            replay = await uow.idempotency.get(
                operation=self.OPERATION, key=command.idempotency_key
            )
            if replay is not None:
                if replay.request_hash != request_hash:
                    raise IdempotencyConflictError(
                        "The idempotency key was already used for a different request.",
                        details={"idempotencyKey": command.idempotency_key},
                    )
                return _candidate_result_from_replay(replay)

            source_id = command.source_ids[0]
            await uow.lock_idempotency(
                operation="context_snapshot",
                key=f"{command.source_type}:{source_id}:{command.content_hash}",
            )
            snapshot = await uow.context_snapshots.find_by_source_hash(
                source_type=command.source_type,
                source_id=source_id,
                content_hash=command.content_hash,
            )
            if snapshot is None:
                snapshot = ContextSnapshot(
                    id=uuid4(),
                    source_type=command.source_type,
                    source_id=source_id,
                    source_ids=command.source_ids,
                    message_ids=command.message_ids,
                    file_ids=command.file_ids,
                    relevant_matter_ids=command.relevant_matter_ids,
                    participant_ids=command.participant_ids,
                    permission_snapshot=command.permission_snapshot,
                    generated_at=command.generated_at,
                    content_hash=command.content_hash,
                )
                await uow.context_snapshots.add(snapshot)
            elif not self._snapshot_matches(snapshot, command):
                raise DomainValidationError(
                    "ContextSnapshot content hash conflicts with different snapshot data.",
                    details={"sourceType": command.source_type, "sourceId": source_id},
                )
            candidate = MessageCandidate.create(
                context_snapshot_id=snapshot.id,
                status=command.status,
                legal_relevance=command.legal_relevance,
                message_role=command.message_role,
                recommended_action=command.recommended_action,
                confidence=command.confidence,
                title_proposal=command.title_proposal,
                category_proposals=command.category_proposals,
                deadline_proposals=command.deadline_proposals,
                related_matter_proposals=command.related_matter_proposals,
                evidence_refs=command.evidence_refs,
                agent_run_id=command.agent_run_id,
            )
            await uow.candidates.add(candidate)
            event_payload: dict[str, object] = {
                "candidateId": str(candidate.id),
                "contextSnapshotId": str(snapshot.id),
                "recommendedAction": candidate.recommended_action.value,
            }
            await uow.audit_events.add(
                AuditEvent(
                    id=uuid4(),
                    aggregate_type="message_candidate",
                    aggregate_id=candidate.id,
                    event_type="message_candidate_created",
                    actor_id=command.actor_id,
                    payload=event_payload,
                    correlation_id=command.correlation_id,
                )
            )
            await uow.outbox_events.add(
                OutboxEvent(
                    id=uuid4(),
                    event_type="MessageCandidateCreated",
                    aggregate_type="message_candidate",
                    aggregate_id=candidate.id,
                    payload=event_payload,
                    correlation_id=command.correlation_id,
                )
            )
            await uow.idempotency.add(
                IdempotencyRecord(
                    id=uuid4(),
                    operation=self.OPERATION,
                    idempotency_key=command.idempotency_key,
                    request_hash=request_hash,
                    response_payload={
                        "candidateId": str(candidate.id),
                        "version": candidate.version,
                    },
                )
            )
            await uow.commit()
        return CandidateCreatedResult(
            candidate_id=candidate.id, version=candidate.version
        )

    @staticmethod
    def _snapshot_matches(
        snapshot: ContextSnapshot, command: CreateCandidateCommand
    ) -> bool:
        return (
            snapshot.source_ids == command.source_ids
            and snapshot.message_ids == command.message_ids
            and snapshot.file_ids == command.file_ids
            and snapshot.relevant_matter_ids == command.relevant_matter_ids
            and snapshot.participant_ids == command.participant_ids
            and snapshot.permission_snapshot == command.permission_snapshot
            and snapshot.generated_at == command.generated_at
        )


class ConfirmCandidateCreateMatterHandler:
    OPERATION = "confirm_candidate_create_matter"

    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def execute(self, command: ConfirmCandidateCreateMatterCommand) -> MatterCreatedResult:
        if not command.initial_work_items:
            raise DomainValidationError(
                "At least one initial work item is required when creating a matter."
            )
        request_payload: dict[str, object] = {
            "candidateId": str(command.candidate_id),
            "candidateVersion": command.candidate_version,
            "title": command.title,
            "primaryCategory": command.primary_category.value,
            "secondaryCategories": [item.value for item in command.secondary_categories],
            "ownerId": command.owner_id,
            "requesterIds": command.requester_ids,
            "legalRisk": command.legal_risk.value,
            "businessImpact": command.business_impact.value,
            "confidentiality": command.confidentiality.value,
            "summary": command.summary,
            "objective": command.objective,
            "initialWorkItems": [
                {
                    "title": item.title,
                    "ownerId": item.owner_id,
                    "priority": item.priority.value,
                    "prioritySource": item.priority_source.value,
                    "nextAction": item.next_action,
                    "priorityReasons": item.priority_reasons,
                    "aiSuggestedPriority": (
                        item.ai_suggested_priority.value if item.ai_suggested_priority else None
                    ),
                    "estimatedMinutes": item.estimated_minutes,
                    "plannedCompleteAt": item.planned_complete_at,
                }
                for item in command.initial_work_items
            ],
        }
        request_hash = _request_hash(request_payload)

        async with self._uow_factory() as uow:
            await uow.lock_idempotency(
                operation=self.OPERATION, key=command.idempotency_key
            )
            replay = await uow.idempotency.get(
                operation=self.OPERATION, key=command.idempotency_key
            )
            if replay is not None:
                if replay.request_hash != request_hash:
                    raise IdempotencyConflictError(
                        "The idempotency key was already used for a different request.",
                        details={"idempotencyKey": command.idempotency_key},
                    )
                return _matter_result_from_replay(replay)

            candidate = await uow.candidates.get_for_update(command.candidate_id)
            if candidate is None:
                raise EntityNotFoundError(
                    "Message candidate was not found.",
                    details={"candidateId": str(command.candidate_id)},
                )
            candidate.confirm_create_matter(
                actor_id=command.actor_id, expected_version=command.candidate_version
            )

            matter = LegalMatter.create(
                title=command.title,
                primary_category=command.primary_category,
                secondary_categories=command.secondary_categories,
                owner_id=command.owner_id,
                legal_risk=command.legal_risk,
                business_impact=command.business_impact,
                confidentiality=command.confidentiality,
                requester_ids=command.requester_ids,
                summary=command.summary,
                objective=command.objective,
            )
            work_items = [
                WorkItem.create(
                    matter_id=matter.id,
                    title=item.title,
                    owner_id=item.owner_id,
                    priority=item.priority,
                    priority_source=item.priority_source,
                    next_action=item.next_action,
                    priority_reasons=item.priority_reasons,
                    ai_suggested_priority=item.ai_suggested_priority,
                    estimated_minutes=item.estimated_minutes,
                    planned_complete_at=item.planned_complete_at,
                    sequence_order=index,
                )
                for index, item in enumerate(command.initial_work_items)
            ]

            await uow.candidates.save(candidate)
            await uow.matters.add(matter)
            await uow.work_items.add_many(work_items)
            await uow.candidates.link_to_matter(
                candidate_id=candidate.id,
                matter_id=matter.id,
                relation_type=CandidateMatterRelation.CREATED,
                confirmed_by=command.actor_id,
            )

            audit_payload: dict[str, object] = {
                "candidateId": str(candidate.id),
                "matterId": str(matter.id),
                "workItemIds": [str(item.id) for item in work_items],
            }
            await uow.audit_events.add(
                AuditEvent(
                    id=uuid4(),
                    aggregate_type="legal_matter",
                    aggregate_id=matter.id,
                    event_type="candidate_confirmed_matter_created",
                    actor_id=command.actor_id,
                    payload=audit_payload,
                    correlation_id=command.correlation_id,
                )
            )
            await uow.outbox_events.add(
                OutboxEvent(
                    id=uuid4(),
                    event_type="LegalMatterCreated",
                    aggregate_type="legal_matter",
                    aggregate_id=matter.id,
                    payload=audit_payload,
                    correlation_id=command.correlation_id,
                )
            )
            await uow.outbox_events.add(
                _legal_butler_requested_event(
                    candidate=candidate,
                    matter=matter,
                    work_item_id=work_items[0].id,
                    actor_id=command.actor_id,
                    correlation_id=command.correlation_id,
                )
            )

            response_payload: dict[str, object] = {
                "matterId": str(matter.id),
                "matterNumber": matter.matter_number,
                "workItemIds": [str(item.id) for item in work_items],
            }
            await uow.idempotency.add(
                IdempotencyRecord(
                    id=uuid4(),
                    operation=self.OPERATION,
                    idempotency_key=command.idempotency_key,
                    request_hash=request_hash,
                    response_payload=response_payload,
                )
            )
            await uow.commit()

        return MatterCreatedResult(
            matter_id=matter.id,
            matter_number=matter.matter_number,
            work_item_ids=[item.id for item in work_items],
        )


class ResolveCandidateHandler:
    OPERATION = "resolve_message_candidate"

    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def execute(self, command: ResolveCandidateCommand) -> CandidateResolvedResult:
        if command.action == CandidateResolutionAction.UPDATE_EXISTING:
            raise DomainValidationError(
                "Updating an existing matter requires a human-reviewed update proposal.",
                details={
                    "endpoint": (
                        f"/api/v1/inbox/candidates/{command.candidate_id}/"
                        "matter-update-proposals"
                    )
                },
            )
        requires_matter = command.action in {
            CandidateResolutionAction.LINK_EXISTING,
        }
        if requires_matter != (command.matter_id is not None):
            raise DomainValidationError(
                "A matter ID is required only for link/update candidate actions."
            )
        request_payload: dict[str, object] = {
            "candidateId": str(command.candidate_id),
            "candidateVersion": command.candidate_version,
            "action": command.action.value,
            "matterId": str(command.matter_id) if command.matter_id else None,
        }
        request_hash = _request_hash(request_payload)
        async with self._uow_factory() as uow:
            await uow.lock_idempotency(
                operation=self.OPERATION, key=command.idempotency_key
            )
            replay = await uow.idempotency.get(
                operation=self.OPERATION, key=command.idempotency_key
            )
            if replay is not None:
                if replay.request_hash != request_hash:
                    raise IdempotencyConflictError(
                        "The idempotency key was already used for another resolution."
                    )
                return _resolved_result_from_replay(replay)
            candidate = await uow.candidates.get_for_update(command.candidate_id)
            if candidate is None:
                raise EntityNotFoundError(
                    "Message candidate was not found.",
                    details={"candidateId": str(command.candidate_id)},
                )
            if command.matter_id is not None:
                matter = await uow.matters.get(command.matter_id)
                if matter is None:
                    raise EntityNotFoundError(
                        "Legal matter was not found.",
                        details={"matterId": str(command.matter_id)},
                    )
            candidate.resolve(
                action=command.action,
                actor_id=command.actor_id,
                expected_version=command.candidate_version,
            )
            await uow.candidates.save(candidate)
            if command.matter_id is not None:
                await uow.candidates.link_to_matter(
                    candidate_id=candidate.id,
                    matter_id=command.matter_id,
                    relation_type=CandidateMatterRelation.LINKED,
                    confirmed_by=command.actor_id,
                )
            response_payload: dict[str, object] = {
                "candidateId": str(candidate.id),
                "status": candidate.status.value,
                "matterId": str(command.matter_id) if command.matter_id else None,
                "version": candidate.version,
            }
            await uow.audit_events.add(
                AuditEvent(
                    id=uuid4(),
                    aggregate_type="message_candidate",
                    aggregate_id=candidate.id,
                    event_type="message_candidate_resolved",
                    actor_id=command.actor_id,
                    payload={**request_payload, "status": candidate.status.value},
                    correlation_id=command.correlation_id,
                )
            )
            await uow.outbox_events.add(
                OutboxEvent(
                    id=uuid4(),
                    event_type="MessageCandidateResolved",
                    aggregate_type="message_candidate",
                    aggregate_id=candidate.id,
                    payload=response_payload,
                    correlation_id=command.correlation_id,
                )
            )
            if command.matter_id is not None:
                if matter is None:
                    raise EntityNotFoundError("Legal matter was not found.")
                await uow.outbox_events.add(
                    _legal_butler_requested_event(
                        candidate=candidate,
                        matter=matter,
                        work_item_id=None,
                        actor_id=command.actor_id,
                        correlation_id=command.correlation_id,
                    )
                )
            await uow.idempotency.add(
                IdempotencyRecord(
                    id=uuid4(),
                    operation=self.OPERATION,
                    idempotency_key=command.idempotency_key,
                    request_hash=request_hash,
                    response_payload=response_payload,
                )
            )
            await uow.commit()
        return CandidateResolvedResult(
            candidate_id=candidate.id,
            status=candidate.status,
            matter_id=command.matter_id,
            version=candidate.version,
        )


class AddWorkItemHandler:
    OPERATION = "add_work_item"

    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def execute(self, command: AddWorkItemCommand) -> WorkItemCreatedResult:
        request_payload: dict[str, object] = {
            "matterId": str(command.matter_id),
            "title": command.title,
            "ownerId": command.owner_id,
            "priority": command.priority.value,
            "prioritySource": command.priority_source.value,
            "nextAction": command.next_action,
            "priorityReasons": command.priority_reasons,
            "aiSuggestedPriority": (
                command.ai_suggested_priority.value if command.ai_suggested_priority else None
            ),
            "estimatedMinutes": command.estimated_minutes,
            "plannedCompleteAt": command.planned_complete_at,
        }
        request_hash = _request_hash(request_payload)

        async with self._uow_factory() as uow:
            await uow.lock_idempotency(
                operation=self.OPERATION, key=command.idempotency_key
            )
            replay = await uow.idempotency.get(
                operation=self.OPERATION, key=command.idempotency_key
            )
            if replay is not None:
                if replay.request_hash != request_hash:
                    raise IdempotencyConflictError(
                        "The idempotency key was already used for a different request.",
                        details={"idempotencyKey": command.idempotency_key},
                    )
                return _work_item_result_from_replay(replay)

            matter = await uow.matters.get_for_update(command.matter_id)
            if matter is None:
                raise EntityNotFoundError(
                    "Legal matter was not found.",
                    details={"matterId": str(command.matter_id)},
                )

            existing = await uow.work_items.list_by_matter(command.matter_id)
            work_item = WorkItem.create(
                matter_id=command.matter_id,
                title=command.title,
                owner_id=command.owner_id,
                priority=command.priority,
                priority_source=command.priority_source,
                next_action=command.next_action,
                priority_reasons=command.priority_reasons,
                ai_suggested_priority=command.ai_suggested_priority,
                estimated_minutes=command.estimated_minutes,
                planned_complete_at=command.planned_complete_at,
                sequence_order=len(existing),
            )
            await uow.work_items.add(work_item)
            await uow.audit_events.add(
                AuditEvent(
                    id=uuid4(),
                    aggregate_type="work_item",
                    aggregate_id=work_item.id,
                    event_type="work_item_created",
                    actor_id=command.actor_id,
                    payload={"matterId": str(command.matter_id)},
                    correlation_id=command.correlation_id,
                )
            )
            await uow.outbox_events.add(
                OutboxEvent(
                    id=uuid4(),
                    event_type="WorkItemCreated",
                    aggregate_type="work_item",
                    aggregate_id=work_item.id,
                    payload={"matterId": str(command.matter_id)},
                    correlation_id=command.correlation_id,
                )
            )
            await uow.idempotency.add(
                IdempotencyRecord(
                    id=uuid4(),
                    operation=self.OPERATION,
                    idempotency_key=command.idempotency_key,
                    request_hash=request_hash,
                    response_payload={
                        "workItemId": str(work_item.id),
                        "matterId": str(command.matter_id),
                    },
                )
            )
            await uow.commit()
        return WorkItemCreatedResult(
            work_item_id=work_item.id, matter_id=command.matter_id
        )
