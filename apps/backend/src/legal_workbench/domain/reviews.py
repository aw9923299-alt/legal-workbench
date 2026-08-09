from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4

from legal_workbench.domain.common import (
    text_hash,
    utc_now,
)
from legal_workbench.domain.enums import (
    CommunicationChannel,
    CommunicationStatus,
    ReviewDecision,
    ReviewPackageStatus,
    ReviewPackageType,
)
from legal_workbench.domain.errors import (
    DomainValidationError,
    EntityVersionConflictError,
    InvalidStateTransitionError,
)


@dataclass(slots=True)
class ReviewPackage:
    id: UUID
    matter_id: UUID
    package_type: ReviewPackageType
    title: str
    background: str
    confirmed_facts: list[dict[str, object]]
    unconfirmed_facts: list[dict[str, object]]
    reasoning: str
    risks: list[dict[str, object]]
    alternatives: list[dict[str, object]]
    citations: list[dict[str, object]]
    proposed_content: str
    target: dict[str, object]
    created_by: str
    work_item_id: UUID | None = None
    grounding_payload: dict[str, object] = field(default_factory=dict)
    status: ReviewPackageStatus = ReviewPackageStatus.DRAFT
    submitted_at: datetime | None = None
    approved_content_hash: str | None = None
    version: int = 1

    @classmethod
    def create(
        cls,
        *,
        matter_id: UUID,
        work_item_id: UUID | None,
        package_type: ReviewPackageType,
        title: str,
        background: str,
        confirmed_facts: list[dict[str, object]],
        unconfirmed_facts: list[dict[str, object]],
        reasoning: str,
        risks: list[dict[str, object]],
        alternatives: list[dict[str, object]],
        citations: list[dict[str, object]],
        proposed_content: str,
        target: dict[str, object],
        created_by: str,
        grounding_payload: dict[str, object] | None = None,
    ) -> ReviewPackage:
        if not title.strip() or not background.strip() or not reasoning.strip():
            raise DomainValidationError(
                "Review package title, background and reasoning are required."
            )
        if not proposed_content.strip():
            raise DomainValidationError("Review package proposed content is required.")
        if not target:
            raise DomainValidationError("Review package target is required.")
        if package_type == ReviewPackageType.EXTERNAL_MESSAGE:
            reply_to = str(target.get("replyToMessageId") or "").strip()
            receive_id = str(target.get("receiveId") or "").strip()
            if not reply_to and not receive_id:
                raise DomainValidationError(
                    "An external message requires replyToMessageId or receiveId."
                )
        return cls(
            id=uuid4(),
            matter_id=matter_id,
            work_item_id=work_item_id,
            package_type=package_type,
            title=title.strip(),
            background=background.strip(),
            confirmed_facts=confirmed_facts,
            unconfirmed_facts=unconfirmed_facts,
            reasoning=reasoning.strip(),
            risks=risks,
            alternatives=alternatives,
            citations=citations,
            proposed_content=proposed_content.strip(),
            target=target,
            created_by=created_by,
            grounding_payload=grounding_payload or {},
        )

    def submit(self, *, expected_version: int) -> None:
        if self.version != expected_version:
            raise EntityVersionConflictError("The review package was changed by another operation.")
        if self.status != ReviewPackageStatus.DRAFT:
            raise InvalidStateTransitionError("Only a draft review package can be submitted.")
        self.status = ReviewPackageStatus.PENDING_REVIEW
        self.submitted_at = utc_now()

    def apply_review(
        self,
        *,
        decision: ReviewDecision,
        final_content: str | None,
        expected_version: int,
    ) -> str | None:
        if self.version != expected_version:
            raise EntityVersionConflictError("The review package was changed by another operation.")
        if self.status != ReviewPackageStatus.PENDING_REVIEW:
            raise InvalidStateTransitionError("Only a pending review package can be reviewed.")
        approved_content: str | None = None
        if decision in {ReviewDecision.APPROVED, ReviewDecision.APPROVED_WITH_EDITS}:
            approved_content = (final_content or self.proposed_content).strip()
            if not approved_content:
                raise DomainValidationError("Approved content cannot be empty.")
            self.status = ReviewPackageStatus.APPROVED
            self.approved_content_hash = text_hash(approved_content)
        elif decision == ReviewDecision.REJECTED:
            self.status = ReviewPackageStatus.REJECTED
        else:
            self.status = ReviewPackageStatus.NEEDS_INFORMATION
        return approved_content


@dataclass(slots=True)
class ReviewRecord:
    id: UUID
    review_package_id: UUID
    reviewer_id: str
    decision: ReviewDecision
    comments: str | None
    final_content: str | None
    final_content_hash: str | None
    change_summary: list[dict[str, object]]
    reusable_as_example: bool
    reviewed_at: datetime = field(default_factory=utc_now)


@dataclass(slots=True)
class Communication:
    id: UUID
    matter_id: UUID
    review_package_id: UUID
    review_record_id: UUID
    channel: CommunicationChannel
    target: dict[str, object]
    content: str
    content_hash: str
    status: CommunicationStatus
    requested_by: str
    correlation_id: str
    work_item_id: UUID | None = None
    external_message_id: str | None = None
    attempts: int = 0
    last_error: str | None = None
    queued_at: datetime | None = None
    sent_at: datetime | None = None
    version: int = 1

    @classmethod
    def create_from_approved_review(
        cls,
        *,
        package: ReviewPackage,
        record: ReviewRecord,
        actor_id: str,
        correlation_id: str,
    ) -> Communication:
        if package.status != ReviewPackageStatus.APPROVED:
            raise InvalidStateTransitionError("Only an approved review package can be sent.")
        if record.decision not in {
            ReviewDecision.APPROVED,
            ReviewDecision.APPROVED_WITH_EDITS,
        }:
            raise InvalidStateTransitionError("The latest review record does not approve sending.")
        content = (record.final_content or package.proposed_content).strip()
        content_digest = text_hash(content)
        if package.approved_content_hash != content_digest:
            raise InvalidStateTransitionError(
                "The message content no longer matches the approved review version."
            )
        return cls(
            id=uuid4(),
            matter_id=package.matter_id,
            work_item_id=package.work_item_id,
            review_package_id=package.id,
            review_record_id=record.id,
            channel=CommunicationChannel.FEISHU,
            target=package.target,
            content=content,
            content_hash=content_digest,
            status=CommunicationStatus.QUEUED,
            requested_by=actor_id,
            correlation_id=correlation_id,
            queued_at=utc_now(),
        )
