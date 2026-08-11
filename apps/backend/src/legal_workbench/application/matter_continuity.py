from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from legal_workbench.application.ports import UnitOfWork
from legal_workbench.domain.entities import FeishuMessage

REPLY_TO_COMMUNICATION_CONFIDENCE = 1.0
SAME_THREAD_CONFIRMED_LINK_CONFIDENCE = 0.95


@dataclass(frozen=True, slots=True)
class MatterContinuityProposal:
    matter_id: UUID
    matter_number: str
    title: str
    confidence: float
    signals: tuple[str, ...]
    evidence_refs: tuple[str, ...]

    def to_payload(self) -> dict[str, object]:
        return {
            "matterId": str(self.matter_id),
            "matterNumber": self.matter_number,
            "title": self.title,
            "confidence": self.confidence,
            "signals": list(self.signals),
            "evidenceRefs": list(self.evidence_refs),
        }


@dataclass(slots=True)
class _ProposalEvidence:
    confidence: float
    signals: list[str]
    evidence_refs: list[str]

    def add(
        self,
        *,
        confidence: float,
        signal: str,
        evidence_refs: Sequence[str],
    ) -> None:
        self.confidence = max(self.confidence, confidence)
        if signal not in self.signals:
            self.signals.append(signal)
        for value in evidence_refs:
            if value not in self.evidence_refs:
                self.evidence_refs.append(value)


class MatterContinuityResolver:
    """Propose related Matters from authoritative, deterministic conversation facts only."""

    async def resolve(
        self,
        uow: UnitOfWork,
        *,
        current: FeishuMessage,
        context_messages: Sequence[FeishuMessage],
    ) -> list[MatterContinuityProposal]:
        evidence_by_matter: dict[UUID, _ProposalEvidence] = {}

        outbound_refs = list(
            dict.fromkeys(
                value
                for value in (current.parent_id, current.root_id)
                if value and value != current.message_id
            )
        )
        if outbound_refs:
            communications = await uow.communications.list_sent_by_external_message_ids(
                outbound_refs
            )
            for communication in communications:
                matched_external_id = communication.external_message_id
                if matched_external_id is None:
                    continue
                self._add_evidence(
                    evidence_by_matter,
                    matter_id=communication.matter_id,
                    confidence=REPLY_TO_COMMUNICATION_CONFIDENCE,
                    signal="reply_to_communication",
                    evidence_refs=(
                        f"communication:{communication.id}",
                        f"message:{matched_external_id}",
                    ),
                )

        related_prior_messages = [
            message
            for message in context_messages
            if message.id != current.id and self._same_thread_or_root(current, message)
        ]
        if related_prior_messages:
            message_by_id = {message.id: message for message in related_prior_messages}
            confirmed_links = await uow.candidates.list_confirmed_matter_links_for_messages(
                list(message_by_id)
            )
            for message_id, matter_id in confirmed_links:
                source_message = message_by_id.get(message_id)
                if source_message is None:
                    continue
                self._add_evidence(
                    evidence_by_matter,
                    matter_id=matter_id,
                    confidence=SAME_THREAD_CONFIRMED_LINK_CONFIDENCE,
                    signal="same_thread_confirmed_link",
                    evidence_refs=(f"message:{source_message.message_id}",),
                )

        proposals: list[MatterContinuityProposal] = []
        for matter_id, evidence in evidence_by_matter.items():
            matter = await uow.matters.get(matter_id)
            if matter is None:
                continue
            proposals.append(
                MatterContinuityProposal(
                    matter_id=matter.id,
                    matter_number=matter.matter_number,
                    title=matter.title,
                    confidence=evidence.confidence,
                    signals=tuple(evidence.signals),
                    evidence_refs=tuple(evidence.evidence_refs),
                )
            )
        return sorted(
            proposals,
            key=lambda value: (-value.confidence, value.matter_number, str(value.matter_id)),
        )

    @staticmethod
    def _same_thread_or_root(current: FeishuMessage, other: FeishuMessage) -> bool:
        if current.thread_id and current.thread_id == other.thread_id:
            return True
        if current.root_id and current.root_id == other.root_id:
            return True
        if current.parent_id and current.parent_id == other.message_id:
            return True
        if current.root_id and current.root_id == other.message_id:
            return True
        return bool(other.root_id and other.root_id == current.message_id)

    @staticmethod
    def _add_evidence(
        evidence_by_matter: dict[UUID, _ProposalEvidence],
        *,
        matter_id: UUID,
        confidence: float,
        signal: str,
        evidence_refs: Sequence[str],
    ) -> None:
        existing = evidence_by_matter.get(matter_id)
        if existing is None:
            evidence_by_matter[matter_id] = _ProposalEvidence(
                confidence=confidence,
                signals=[signal],
                evidence_refs=list(evidence_refs),
            )
            return
        existing.add(
            confidence=confidence,
            signal=signal,
            evidence_refs=evidence_refs,
        )
