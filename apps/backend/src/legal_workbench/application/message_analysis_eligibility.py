from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from legal_workbench.application.ports import UnitOfWorkFactory
from legal_workbench.domain.entities import AuditEvent


@dataclass(frozen=True, slots=True)
class MessageAnalysisEligibilityDecision:
    allowed: bool
    reason: str
    manual_override: bool


class MessageAnalysisEligibility:
    """Central policy for recalled-message analysis eligibility."""

    @staticmethod
    def evaluate(
        *,
        recalled_at: datetime | None,
        actor_source: str,
        override_recalled: bool = False,
    ) -> MessageAnalysisEligibilityDecision:
        if recalled_at is not None and actor_source == "user" and override_recalled:
            return MessageAnalysisEligibilityDecision(
                allowed=True,
                reason="manual_override",
                manual_override=True,
            )
        if recalled_at is not None:
            return MessageAnalysisEligibilityDecision(
                allowed=False,
                reason="message_recalled",
                manual_override=False,
            )
        return MessageAnalysisEligibilityDecision(
            allowed=True,
            reason="analysis_allowed",
            manual_override=False,
        )


class MessageAnalysisDispatchGuard:
    """Re-check durable message state immediately before outbox dispatch."""

    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def evaluate_and_audit(
        self,
        *,
        message_id: UUID,
        actor_id: str,
        actor_source: str,
        override_recalled: bool,
        correlation_id: str,
    ) -> MessageAnalysisEligibilityDecision:
        async with self._uow_factory() as uow:
            message = await uow.feishu.get_message_for_update(message_id)
            if message is None:
                return MessageAnalysisEligibilityDecision(
                    allowed=False,
                    reason="message_not_found",
                    manual_override=False,
                )
            decision = MessageAnalysisEligibility.evaluate(
                recalled_at=message.recalled_at,
                actor_source=actor_source,
                override_recalled=override_recalled,
            )
            if not decision.allowed or decision.manual_override:
                await uow.audit_events.add(
                    AuditEvent(
                        id=uuid4(),
                        aggregate_type="feishu_message",
                        aggregate_id=message.id,
                        event_type=(
                            "recalled_message_manual_analysis_override_dispatched"
                            if decision.manual_override
                            else "recalled_message_automatic_analysis_dispatch_suppressed"
                        ),
                        actor_id=actor_id,
                        actor_source=actor_source,
                        payload={
                            "reason": decision.reason,
                            "phase": "outbox_dispatch",
                        },
                        correlation_id=correlation_id,
                    )
                )
                await uow.commit()
            return decision
