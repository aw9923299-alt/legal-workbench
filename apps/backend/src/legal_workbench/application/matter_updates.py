from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from legal_workbench.application.handlers import _request_hash
from legal_workbench.application.ports import UnitOfWorkFactory
from legal_workbench.domain.entities import (
    AuditEvent,
    Deadline,
    IdempotencyRecord,
    LegalMatter,
    MatterUpdateProposal,
    MessageCandidate,
    OutboxEvent,
    ProposalFieldDecision,
    WorkItem,
)
from legal_workbench.domain.enums import (
    CandidateMatterRelation,
    CandidateResolutionAction,
    DeadlineSource,
    DeadlineType,
    MatterUpdateProposalStatus,
    Priority,
    PrioritySource,
)
from legal_workbench.domain.errors import (
    DomainValidationError,
    EntityNotFoundError,
    EntityVersionConflictError,
    IdempotencyConflictError,
)


@dataclass(frozen=True, slots=True)
class CreateMatterUpdateProposalCommand:
    candidate_id: UUID
    candidate_version: int
    matter_id: UUID
    proposed_changes: dict[str, dict[str, object]]
    reason: str
    actor_id: str
    correlation_id: str
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class ReviewMatterUpdateProposalCommand:
    proposal_id: UUID
    proposal_version: int
    matter_version: int
    decisions: list[ProposalFieldDecision]
    rejection_reason: str | None
    actor_id: str
    correlation_id: str
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class MatterUpdateProposalCreatedResult:
    proposal_id: UUID
    candidate_id: UUID
    matter_id: UUID
    status: MatterUpdateProposalStatus
    version: int
    idempotent_replay: bool = False


@dataclass(frozen=True, slots=True)
class MatterUpdateProposalReviewedResult:
    proposal_id: UUID
    matter_id: UUID
    status: MatterUpdateProposalStatus
    proposal_version: int
    matter_version: int
    work_item_ids: list[UUID]
    deadline_id: UUID | None
    idempotent_replay: bool = False


def _proposal_created_replay(
    record: IdempotencyRecord,
) -> MatterUpdateProposalCreatedResult:
    return MatterUpdateProposalCreatedResult(
        proposal_id=UUID(str(record.response_payload["proposalId"])),
        candidate_id=UUID(str(record.response_payload["candidateId"])),
        matter_id=UUID(str(record.response_payload["matterId"])),
        status=MatterUpdateProposalStatus(str(record.response_payload["status"])),
        version=int(str(record.response_payload["version"])),
        idempotent_replay=True,
    )


def _proposal_reviewed_replay(
    record: IdempotencyRecord,
) -> MatterUpdateProposalReviewedResult:
    work_item_ids = record.response_payload.get("workItemIds", [])
    if not isinstance(work_item_ids, list):
        raise RuntimeError("Invalid proposal review replay payload")
    deadline_id = record.response_payload.get("deadlineId")
    return MatterUpdateProposalReviewedResult(
        proposal_id=UUID(str(record.response_payload["proposalId"])),
        matter_id=UUID(str(record.response_payload["matterId"])),
        status=MatterUpdateProposalStatus(str(record.response_payload["status"])),
        proposal_version=int(str(record.response_payload["proposalVersion"])),
        matter_version=int(str(record.response_payload["matterVersion"])),
        work_item_ids=[UUID(str(value)) for value in work_item_ids],
        deadline_id=UUID(str(deadline_id)) if deadline_id else None,
        idempotent_replay=True,
    )


class CreateMatterUpdateProposalHandler:
    OPERATION = "create_matter_update_proposal"

    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def execute(
        self, command: CreateMatterUpdateProposalCommand
    ) -> MatterUpdateProposalCreatedResult:
        request_payload: dict[str, object] = {
            "candidateId": str(command.candidate_id),
            "candidateVersion": command.candidate_version,
            "matterId": str(command.matter_id),
            "proposedChanges": command.proposed_changes,
            "reason": command.reason,
        }
        request_hash = _request_hash(request_payload)
        async with self._uow_factory() as uow:
            await uow.lock_idempotency(operation=self.OPERATION, key=command.idempotency_key)
            replay = await uow.idempotency.get(
                operation=self.OPERATION, key=command.idempotency_key
            )
            if replay is not None:
                if replay.request_hash != request_hash:
                    raise IdempotencyConflictError(
                        "The idempotency key was already used for another proposal."
                    )
                return _proposal_created_replay(replay)

            candidate = await uow.candidates.get_for_update(command.candidate_id)
            if candidate is None:
                raise EntityNotFoundError(
                    "Message candidate was not found.",
                    details={"candidateId": str(command.candidate_id)},
                )
            matter = await uow.matters.get(command.matter_id)
            if matter is None:
                raise EntityNotFoundError(
                    "Legal matter was not found.",
                    details={"matterId": str(command.matter_id)},
                )
            proposal = MatterUpdateProposal.create(
                candidate_id=candidate.id,
                matter_id=matter.id,
                base_matter_version=matter.version,
                proposed_changes=self._map_trusted_proposed_changes(
                    requested_fields=set(command.proposed_changes),
                    candidate=candidate,
                    matter=matter,
                ),
                reason=command.reason,
                created_by=command.actor_id,
            )
            candidate.resolve(
                action=CandidateResolutionAction.UPDATE_EXISTING,
                actor_id=command.actor_id,
                expected_version=command.candidate_version,
            )
            await uow.matter_update_proposals.add(proposal)
            await uow.candidates.save(candidate)
            await uow.candidates.link_to_matter(
                candidate_id=candidate.id,
                matter_id=matter.id,
                relation_type=CandidateMatterRelation.UPDATED,
                confirmed_by=command.actor_id,
            )
            response_payload: dict[str, object] = {
                "proposalId": str(proposal.id),
                "candidateId": str(candidate.id),
                "matterId": str(matter.id),
                "status": proposal.status.value,
                "version": proposal.version,
            }
            await uow.audit_events.add(
                AuditEvent(
                    id=uuid4(),
                    aggregate_type="matter_update_proposal",
                    aggregate_id=proposal.id,
                    event_type="matter_update_proposal_created",
                    actor_id=command.actor_id,
                    payload={
                        "candidateId": str(candidate.id),
                        "matterId": str(matter.id),
                        "baseMatterVersion": matter.version,
                        "proposedFields": sorted(proposal.proposed_changes),
                    },
                    correlation_id=command.correlation_id,
                )
            )
            await uow.outbox_events.add(
                OutboxEvent(
                    id=uuid4(),
                    event_type="MatterUpdateProposalCreated",
                    aggregate_type="matter_update_proposal",
                    aggregate_id=proposal.id,
                    payload=response_payload,
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
        return MatterUpdateProposalCreatedResult(
            proposal_id=proposal.id,
            candidate_id=candidate.id,
            matter_id=matter.id,
            status=proposal.status,
            version=proposal.version,
        )

    @staticmethod
    def _map_trusted_proposed_changes(
        *,
        requested_fields: set[str],
        candidate: MessageCandidate,
        matter: LegalMatter,
    ) -> dict[str, dict[str, object]]:
        analysis_payload = candidate.analysis_payload
        raw_extracted_values = analysis_payload.get("messageExtractedValues", {})
        extracted_values = (
            dict(raw_extracted_values) if isinstance(raw_extracted_values, dict) else {}
        )
        category_proposals = candidate.category_proposals
        category_value = (
            category_proposals[0].get("category")
            if category_proposals and isinstance(category_proposals[0], dict)
            else None
        )
        deadline_proposals = candidate.deadline_proposals
        deadline_value = None
        if deadline_proposals and isinstance(deadline_proposals[0], dict):
            deadline_value = deadline_proposals[0].get("resolvedAt") or deadline_proposals[0].get(
                "dueAt"
            )
            extracted_values.setdefault("deadline", deadline_proposals[0].get("rawText"))
        suggested_work_items = analysis_payload.get("suggestedWorkItems", [])
        if not isinstance(suggested_work_items, list):
            suggested_work_items = []
        current_values: dict[str, object] = {
            "title": matter.title,
            "category": matter.primary_category.value,
            "priority": matter.priority.value,
            "deadline": (
                matter.target_deadline_at.isoformat() if matter.target_deadline_at else None
            ),
            "owner": matter.owner_id,
            "currentStatus": matter.work_status.value,
            "nextAction": matter.next_action,
            "newWorkItems": [],
        }
        ai_values: dict[str, object] = {
            "title": candidate.title_proposal,
            "category": category_value,
            "priority": analysis_payload.get("suggestedPriority"),
            "deadline": deadline_value,
            "owner": analysis_payload.get("suggestedOwnerId"),
            "currentStatus": analysis_payload.get("suggestedMatterStatus"),
            "nextAction": analysis_payload.get("suggestedNextAction"),
            "newWorkItems": suggested_work_items,
        }
        return {
            field_name: {
                "currentValue": current_values[field_name],
                "messageExtractedValue": extracted_values.get(field_name),
                "aiSuggestedValue": ai_values[field_name],
            }
            for field_name in MatterUpdateProposal.ALLOWED_FIELDS
            if field_name in requested_fields
        }


class ReviewMatterUpdateProposalHandler:
    OPERATION = "review_matter_update_proposal"

    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def execute(
        self, command: ReviewMatterUpdateProposalCommand
    ) -> MatterUpdateProposalReviewedResult:
        request_payload: dict[str, object] = {
            "proposalId": str(command.proposal_id),
            "proposalVersion": command.proposal_version,
            "matterVersion": command.matter_version,
            "decisions": [
                {
                    "fieldName": item.field_name,
                    "decision": item.decision.value,
                    "finalValue": item.final_value,
                }
                for item in command.decisions
            ],
            "rejectionReason": command.rejection_reason,
        }
        request_hash = _request_hash(request_payload)
        async with self._uow_factory() as uow:
            await uow.lock_idempotency(operation=self.OPERATION, key=command.idempotency_key)
            replay = await uow.idempotency.get(
                operation=self.OPERATION, key=command.idempotency_key
            )
            if replay is not None:
                if replay.request_hash != request_hash:
                    raise IdempotencyConflictError(
                        "The idempotency key was already used for another proposal review."
                    )
                return _proposal_reviewed_replay(replay)

            proposal = await uow.matter_update_proposals.get_for_update(command.proposal_id)
            if proposal is None:
                raise EntityNotFoundError(
                    "Matter update proposal was not found.",
                    details={"proposalId": str(command.proposal_id)},
                )
            matter = await uow.matters.get_for_update(proposal.matter_id)
            if matter is None:
                raise EntityNotFoundError(
                    "Legal matter was not found.",
                    details={"matterId": str(proposal.matter_id)},
                )
            if (
                command.matter_version != proposal.base_matter_version
                or matter.version != proposal.base_matter_version
            ):
                raise EntityVersionConflictError(
                    "The legal matter changed after this proposal was created.",
                    details={
                        "baseMatterVersion": proposal.base_matter_version,
                        "requestedMatterVersion": command.matter_version,
                        "actualMatterVersion": matter.version,
                    },
                )

            approved = proposal.review(
                decisions=command.decisions,
                reviewer_id=command.actor_id,
                rejection_reason=command.rejection_reason,
                expected_version=command.proposal_version,
            )
            scalar_changes = self._parse_scalar_changes(approved)
            work_items = self._build_work_items(
                approved.get("newWorkItems"),
                matter_id=matter.id,
                sequence_start=len(await uow.work_items.list_by_matter(matter.id)),
            )
            deadline = self._build_deadline(
                scalar_changes.get("deadline"),
                matter_id=matter.id,
                proposal_id=proposal.id,
                actor_id=command.actor_id,
            )
            matter.apply_confirmed_changes(
                changes=scalar_changes,
                actor_id=command.actor_id,
                expected_version=proposal.base_matter_version,
            )
            await uow.matter_update_proposals.save(proposal)
            await uow.matters.save(matter)
            await uow.work_items.add_many(work_items)
            if deadline is not None:
                await uow.deadlines.add(deadline)

            response_payload: dict[str, object] = {
                "proposalId": str(proposal.id),
                "matterId": str(matter.id),
                "status": proposal.status.value,
                "proposalVersion": proposal.version,
                "matterVersion": matter.version,
                "workItemIds": [str(item.id) for item in work_items],
                "deadlineId": str(deadline.id) if deadline else None,
            }
            await uow.audit_events.add(
                AuditEvent(
                    id=uuid4(),
                    aggregate_type="matter_update_proposal",
                    aggregate_id=proposal.id,
                    event_type="matter_update_proposal_reviewed",
                    actor_id=command.actor_id,
                    payload={
                        **response_payload,
                        "approvedFields": sorted(approved),
                        "rejectionReason": proposal.rejection_reason,
                    },
                    correlation_id=command.correlation_id,
                )
            )
            await uow.outbox_events.add(
                OutboxEvent(
                    id=uuid4(),
                    event_type="MatterUpdateProposalReviewed",
                    aggregate_type="matter_update_proposal",
                    aggregate_id=proposal.id,
                    payload=response_payload,
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
        return MatterUpdateProposalReviewedResult(
            proposal_id=proposal.id,
            matter_id=matter.id,
            status=proposal.status,
            proposal_version=proposal.version,
            matter_version=matter.version,
            work_item_ids=[item.id for item in work_items],
            deadline_id=deadline.id if deadline else None,
        )

    @staticmethod
    def _parse_scalar_changes(approved: dict[str, object]) -> dict[str, object]:
        scalar = {key: value for key, value in approved.items() if key != "newWorkItems"}
        deadline = scalar.get("deadline")
        if deadline is not None:
            if not isinstance(deadline, str):
                raise DomainValidationError("Matter deadline must use ISO-8601 text.")
            try:
                scalar["deadline"] = datetime.fromisoformat(deadline)
            except ValueError as exc:
                raise DomainValidationError("Matter deadline must use ISO-8601 text.") from exc
        return scalar

    @staticmethod
    def _build_work_items(
        raw_value: object | None, *, matter_id: UUID, sequence_start: int
    ) -> list[WorkItem]:
        if raw_value is None:
            return []
        if not isinstance(raw_value, list):
            raise DomainValidationError("New work items must be a list.")
        work_items: list[WorkItem] = []
        for index, raw_item in enumerate(raw_value):
            if not isinstance(raw_item, dict):
                raise DomainValidationError("Each new work item must be an object.")
            try:
                planned_at_raw = raw_item.get("plannedCompleteAt")
                planned_at = datetime.fromisoformat(str(planned_at_raw)) if planned_at_raw else None
                work_items.append(
                    WorkItem.create(
                        matter_id=matter_id,
                        title=str(raw_item["title"]),
                        owner_id=str(raw_item["ownerId"]),
                        priority=Priority(str(raw_item["priority"])),
                        priority_source=PrioritySource.LEGAL_CONFIRMED,
                        next_action=str(raw_item["nextAction"]),
                        priority_reasons=[
                            str(value) for value in raw_item.get("priorityReasons", [])
                        ],
                        estimated_minutes=(
                            int(str(raw_item["estimatedMinutes"]))
                            if raw_item.get("estimatedMinutes") is not None
                            else None
                        ),
                        planned_complete_at=planned_at,
                        sequence_order=sequence_start + index,
                    )
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise DomainValidationError(
                    "An approved work item has invalid final values."
                ) from exc
        return work_items

    @staticmethod
    def _build_deadline(
        value: object | None,
        *,
        matter_id: UUID,
        proposal_id: UUID,
        actor_id: str,
    ) -> Deadline | None:
        if value is None:
            return None
        if not isinstance(value, datetime):
            raise DomainValidationError("Matter deadline must be a datetime.")
        return Deadline.create(
            deadline_type=DeadlineType.INTERNAL,
            source=DeadlineSource.LEGAL_CONFIRMED,
            due_at=value,
            timezone=str(value.tzinfo),
            is_hard=False,
            matter_id=matter_id,
            work_item_id=None,
            source_reference=f"matter_update_proposal:{proposal_id}",
            confidence=None,
            reminder_policy={},
            actor_id=actor_id,
        )
