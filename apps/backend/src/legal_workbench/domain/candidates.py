from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4

from legal_workbench.domain.common import (
    utc_now,
)
from legal_workbench.domain.enums import (
    CandidateResolutionAction,
    CandidateStatus,
    LegalRelevance,
    MessageRole,
    RecommendedAction,
)
from legal_workbench.domain.errors import (
    DomainValidationError,
    EntityVersionConflictError,
    InvalidStateTransitionError,
)


@dataclass(slots=True)
class MessageCandidate:
    id: UUID
    context_snapshot_id: UUID
    status: CandidateStatus
    legal_relevance: LegalRelevance
    message_role: MessageRole
    recommended_action: RecommendedAction
    confidence: float
    title_proposal: str | None = None
    category_proposals: list[dict[str, object]] = field(default_factory=list)
    deadline_proposals: list[dict[str, object]] = field(default_factory=list)
    related_matter_proposals: list[dict[str, object]] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
    agent_run_id: UUID | None = None
    feishu_message_id: UUID | None = None
    requires_manual_review: bool = True
    analysis_payload: dict[str, object] = field(default_factory=dict)
    confirmed_by: str | None = None
    confirmed_at: datetime | None = None
    version: int = 1

    def __post_init__(self) -> None:
        if not 0 <= self.confidence <= 1:
            raise DomainValidationError(
                "Candidate confidence must be between 0 and 1.",
                details={"confidence": self.confidence},
            )

    @classmethod
    def create(
        cls,
        *,
        context_snapshot_id: UUID,
        status: CandidateStatus,
        legal_relevance: LegalRelevance,
        message_role: MessageRole,
        recommended_action: RecommendedAction,
        confidence: float,
        title_proposal: str | None,
        category_proposals: list[dict[str, object]],
        deadline_proposals: list[dict[str, object]],
        related_matter_proposals: list[dict[str, object]],
        evidence_refs: list[str],
        agent_run_id: UUID | None,
    ) -> MessageCandidate:
        if status not in {
            CandidateStatus.PENDING_ANALYSIS,
            CandidateStatus.PENDING_CONFIRMATION,
        }:
            raise DomainValidationError(
                "A new message candidate must start in a pending status.",
                details={"status": status.value},
            )
        normalized_title = title_proposal.strip() if title_proposal else None
        return cls(
            id=uuid4(),
            context_snapshot_id=context_snapshot_id,
            status=status,
            legal_relevance=legal_relevance,
            message_role=message_role,
            recommended_action=recommended_action,
            confidence=confidence,
            title_proposal=normalized_title or None,
            category_proposals=category_proposals,
            deadline_proposals=deadline_proposals,
            related_matter_proposals=related_matter_proposals,
            evidence_refs=evidence_refs,
            agent_run_id=agent_run_id,
        )

    def confirm_create_matter(self, *, actor_id: str, expected_version: int) -> None:
        if self.version != expected_version:
            raise EntityVersionConflictError(
                "The message candidate was changed by another operation.",
                details={"expectedVersion": expected_version, "actualVersion": self.version},
            )
        if self.status not in {
            CandidateStatus.PENDING_ANALYSIS,
            CandidateStatus.PENDING_CONFIRMATION,
        }:
            raise InvalidStateTransitionError(
                "Only a pending candidate can create a legal matter.",
                details={"candidateId": str(self.id), "status": self.status.value},
            )
        if self.legal_relevance not in {
            LegalRelevance.RELEVANT,
            LegalRelevance.POSSIBLY_RELEVANT,
        }:
            raise InvalidStateTransitionError(
                "A non-legal candidate cannot create a legal matter.",
                details={"legalRelevance": self.legal_relevance.value},
            )
        self.status = CandidateStatus.CONFIRMED
        self.confirmed_by = actor_id
        self.confirmed_at = utc_now()

    def resolve(
        self,
        *,
        action: CandidateResolutionAction,
        actor_id: str,
        expected_version: int,
    ) -> None:
        if self.version != expected_version:
            raise EntityVersionConflictError(
                "The message candidate was changed by another operation.",
                details={"expectedVersion": expected_version, "actualVersion": self.version},
            )
        if self.status not in {
            CandidateStatus.PENDING_ANALYSIS,
            CandidateStatus.PENDING_CONFIRMATION,
        }:
            raise InvalidStateTransitionError(
                "Only a pending candidate can be resolved.",
                details={"candidateId": str(self.id), "status": self.status.value},
            )
        self.status = {
            CandidateResolutionAction.LINK_EXISTING: CandidateStatus.LINKED,
            CandidateResolutionAction.UPDATE_EXISTING: CandidateStatus.LINKED,
            CandidateResolutionAction.INFORMATION_ONLY: CandidateStatus.INFORMATION_ONLY,
            CandidateResolutionAction.IGNORE: CandidateStatus.IGNORED,
        }[action]
        self.confirmed_by = actor_id
        self.confirmed_at = utc_now()
        self.version += 1

    def replace_pending_analysis(
        self,
        *,
        context_snapshot_id: UUID,
        legal_relevance: LegalRelevance,
        message_role: MessageRole,
        recommended_action: RecommendedAction,
        confidence: float,
        title_proposal: str | None,
        category_proposals: list[dict[str, object]],
        deadline_proposals: list[dict[str, object]],
        evidence_refs: list[str],
        agent_run_id: UUID,
        requires_manual_review: bool,
        analysis_payload: dict[str, object],
    ) -> None:
        if self.status not in {
            CandidateStatus.PENDING_ANALYSIS,
            CandidateStatus.PENDING_CONFIRMATION,
        }:
            raise InvalidStateTransitionError(
                "Only a pending candidate can be replaced by a later AgentRun.",
                details={"candidateId": str(self.id), "status": self.status.value},
            )
        if not 0 <= confidence <= 1:
            raise DomainValidationError("Candidate confidence must be between 0 and 1.")
        self.context_snapshot_id = context_snapshot_id
        self.status = CandidateStatus.PENDING_CONFIRMATION
        self.legal_relevance = legal_relevance
        self.message_role = message_role
        self.recommended_action = recommended_action
        self.confidence = confidence
        self.title_proposal = title_proposal.strip() if title_proposal else None
        self.category_proposals = category_proposals
        self.deadline_proposals = deadline_proposals
        self.evidence_refs = evidence_refs
        self.agent_run_id = agent_run_id
        self.requires_manual_review = requires_manual_review
        self.analysis_payload = analysis_payload
        self.version += 1

    def reject_superseded_analysis(self) -> None:
        if self.status not in {
            CandidateStatus.PENDING_ANALYSIS,
            CandidateStatus.PENDING_CONFIRMATION,
        }:
            raise InvalidStateTransitionError(
                "Only a pending candidate can be superseded by a later analysis.",
                details={"candidateId": str(self.id), "status": self.status.value},
            )
        self.status = CandidateStatus.REJECTED
        self.version += 1
