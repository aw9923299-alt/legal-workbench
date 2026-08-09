from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

from legal_workbench.application.message_analysis_eligibility import (
    MessageAnalysisEligibility,
)
from legal_workbench.application.ports import UnitOfWork
from legal_workbench.domain.entities import OutboxEvent


@dataclass(frozen=True, slots=True)
class AutomaticAnalysisDecision:
    requested: bool
    reason: str


class AutomaticAnalysisGate:
    """The only policy boundary for automatically enqueued message analysis."""

    EVENT_TYPE = "FeishuMessageAnalysisRequested"

    async def request_if_allowed(
        self,
        uow: UnitOfWork,
        message_id: UUID,
        *,
        actor_id: str,
        actor_source: str,
        correlation_id: str,
        force_new_run: bool = False,
    ) -> AutomaticAnalysisDecision:
        await uow.lock_idempotency(
            operation="automatic_message_analysis",
            key=str(message_id),
        )
        message = await uow.feishu.get_message_by_id(message_id)
        if message is None:
            return AutomaticAnalysisDecision(False, "message_not_found")
        eligibility = MessageAnalysisEligibility.evaluate(
            recalled_at=message.recalled_at,
            actor_source=actor_source,
        )
        if not eligibility.allowed:
            return AutomaticAnalysisDecision(False, eligibility.reason)
        if message.analysis_disposition != "analyze":
            return AutomaticAnalysisDecision(
                False,
                f"message_disposition_{message.analysis_disposition}",
            )
        if await uow.outbox_events.exists_pending(
            event_type=self.EVENT_TYPE,
            aggregate_id=message_id,
        ):
            return AutomaticAnalysisDecision(False, "analysis_already_pending")
        await uow.outbox_events.add(
            OutboxEvent(
                id=uuid4(),
                event_type=self.EVENT_TYPE,
                aggregate_type="feishu_message",
                aggregate_id=message_id,
                payload={
                    "messageId": str(message_id),
                    "actorId": actor_id,
                    "actorSource": actor_source,
                    "forceNewRun": bool(force_new_run or message.version > 1),
                },
                correlation_id=correlation_id,
            )
        )
        return AutomaticAnalysisDecision(True, "analysis_requested")
