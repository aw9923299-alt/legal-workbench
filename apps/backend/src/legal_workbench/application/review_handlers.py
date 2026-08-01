from __future__ import annotations

from uuid import uuid4

from legal_workbench.application.commands import (
    CreateReviewPackageCommand,
    QueueCommunicationCommand,
    ReviewPackageCommand,
    SubmitReviewPackageCommand,
)
from legal_workbench.application.idempotency import (
    replay_uuid,
    request_hash,
    require_matching_replay,
)
from legal_workbench.application.ports import UnitOfWorkFactory
from legal_workbench.application.results import (
    CommunicationQueuedResult,
    ReviewPackageCreatedResult,
    ReviewRecordedResult,
)
from legal_workbench.domain.entities import (
    AuditEvent,
    Communication,
    IdempotencyRecord,
    OutboxEvent,
    ReviewPackage,
    ReviewRecord,
    text_hash,
)
from legal_workbench.domain.errors import EntityNotFoundError


class CreateReviewPackageHandler:
    OPERATION = "create_review_package"

    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def execute(
        self, command: CreateReviewPackageCommand
    ) -> ReviewPackageCreatedResult:
        payload = {
            "matterId": str(command.matter_id),
            "workItemId": str(command.work_item_id) if command.work_item_id else None,
            "packageType": command.package_type.value,
            "title": command.title,
            "background": command.background,
            "confirmedFacts": command.confirmed_facts,
            "unconfirmedFacts": command.unconfirmed_facts,
            "reasoning": command.reasoning,
            "risks": command.risks,
            "alternatives": command.alternatives,
            "citations": command.citations,
            "proposedContent": command.proposed_content,
            "target": command.target,
            "submitForReview": command.submit_for_review,
        }
        digest = request_hash(payload)
        async with self._uow_factory() as uow:
            await uow.lock_idempotency(operation=self.OPERATION, key=command.idempotency_key)
            replay = require_matching_replay(
                await uow.idempotency.get(
                    operation=self.OPERATION, key=command.idempotency_key
                ),
                expected_hash=digest,
                idempotency_key=command.idempotency_key,
            )
            if replay is not None:
                return ReviewPackageCreatedResult(
                    review_package_id=replay_uuid(replay, "reviewPackageId"),
                    version=int(str(replay.response_payload["version"])),
                    idempotent_replay=True,
                )
            if await uow.matters.get(command.matter_id) is None:
                raise EntityNotFoundError("Legal matter was not found.")
            if command.work_item_id is not None:
                work_item = await uow.work_items.get(command.work_item_id)
                if work_item is None:
                    raise EntityNotFoundError("Work item was not found.")
                if work_item.matter_id != command.matter_id:
                    raise EntityNotFoundError(
                        "Work item does not belong to the selected legal matter."
                    )
            package = ReviewPackage.create(
                matter_id=command.matter_id,
                work_item_id=command.work_item_id,
                package_type=command.package_type,
                title=command.title,
                background=command.background,
                confirmed_facts=command.confirmed_facts,
                unconfirmed_facts=command.unconfirmed_facts,
                reasoning=command.reasoning,
                risks=command.risks,
                alternatives=command.alternatives,
                citations=command.citations,
                proposed_content=command.proposed_content,
                target=command.target,
                created_by=command.actor_id,
            )
            if command.submit_for_review:
                package.submit(expected_version=package.version)
            await uow.review_packages.add(package)
            event_payload: dict[str, object] = {
                "reviewPackageId": str(package.id),
                "matterId": str(package.matter_id),
                "workItemId": str(package.work_item_id) if package.work_item_id else None,
                "status": package.status.value,
            }
            await uow.audit_events.add(
                AuditEvent(
                    id=uuid4(),
                    aggregate_type="review_package",
                    aggregate_id=package.id,
                    event_type="review_package_created",
                    actor_id=command.actor_id,
                    payload=event_payload,
                    correlation_id=command.correlation_id,
                )
            )
            await uow.outbox_events.add(
                OutboxEvent(
                    id=uuid4(),
                    event_type="ReviewPackageCreated",
                    aggregate_type="review_package",
                    aggregate_id=package.id,
                    payload=event_payload,
                    correlation_id=command.correlation_id,
                )
            )
            await uow.idempotency.add(
                IdempotencyRecord(
                    id=uuid4(),
                    operation=self.OPERATION,
                    idempotency_key=command.idempotency_key,
                    request_hash=digest,
                    response_payload={
                        "reviewPackageId": str(package.id),
                        "version": package.version,
                    },
                )
            )
            await uow.commit()
        return ReviewPackageCreatedResult(
            review_package_id=package.id, version=package.version
        )


class SubmitReviewPackageHandler:
    OPERATION = "submit_review_package"

    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def execute(
        self, command: SubmitReviewPackageCommand
    ) -> ReviewPackageCreatedResult:
        payload = {
            "reviewPackageId": str(command.review_package_id),
            "packageVersion": command.package_version,
        }
        digest = request_hash(payload)
        async with self._uow_factory() as uow:
            await uow.lock_idempotency(operation=self.OPERATION, key=command.idempotency_key)
            replay = require_matching_replay(
                await uow.idempotency.get(
                    operation=self.OPERATION, key=command.idempotency_key
                ),
                expected_hash=digest,
                idempotency_key=command.idempotency_key,
            )
            if replay is not None:
                return ReviewPackageCreatedResult(
                    review_package_id=replay_uuid(replay, "reviewPackageId"),
                    version=int(str(replay.response_payload["version"])),
                    idempotent_replay=True,
                )
            package = await uow.review_packages.get_for_update(command.review_package_id)
            if package is None:
                raise EntityNotFoundError("Review package was not found.")
            package.submit(expected_version=command.package_version)
            await uow.review_packages.save(package)
            next_version = package.version + 1
            await uow.audit_events.add(
                AuditEvent(
                    id=uuid4(),
                    aggregate_type="review_package",
                    aggregate_id=package.id,
                    event_type="review_package_submitted",
                    actor_id=command.actor_id,
                    payload={"status": package.status.value},
                    correlation_id=command.correlation_id,
                )
            )
            await uow.idempotency.add(
                IdempotencyRecord(
                    id=uuid4(),
                    operation=self.OPERATION,
                    idempotency_key=command.idempotency_key,
                    request_hash=digest,
                    response_payload={
                        "reviewPackageId": str(package.id),
                        "version": next_version,
                    },
                )
            )
            await uow.commit()
        return ReviewPackageCreatedResult(
            review_package_id=package.id, version=next_version
        )


class ReviewPackageHandler:
    OPERATION = "review_package"

    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def execute(self, command: ReviewPackageCommand) -> ReviewRecordedResult:
        payload = {
            "reviewPackageId": str(command.review_package_id),
            "packageVersion": command.package_version,
            "decision": command.decision.value,
            "comments": command.comments,
            "finalContent": command.final_content,
            "changeSummary": command.change_summary,
            "reusableAsExample": command.reusable_as_example,
        }
        digest = request_hash(payload)
        async with self._uow_factory() as uow:
            await uow.lock_idempotency(operation=self.OPERATION, key=command.idempotency_key)
            replay = require_matching_replay(
                await uow.idempotency.get(
                    operation=self.OPERATION, key=command.idempotency_key
                ),
                expected_hash=digest,
                idempotency_key=command.idempotency_key,
            )
            if replay is not None:
                return ReviewRecordedResult(
                    review_package_id=replay_uuid(replay, "reviewPackageId"),
                    review_record_id=replay_uuid(replay, "reviewRecordId"),
                    status=str(replay.response_payload["status"]),
                    idempotent_replay=True,
                )
            package = await uow.review_packages.get_for_update(command.review_package_id)
            if package is None:
                raise EntityNotFoundError("Review package was not found.")
            approved_content = package.apply_review(
                decision=command.decision,
                final_content=command.final_content,
                expected_version=command.package_version,
            )
            record = ReviewRecord(
                id=uuid4(),
                review_package_id=package.id,
                reviewer_id=command.actor_id,
                decision=command.decision,
                comments=command.comments.strip() if command.comments else None,
                final_content=approved_content,
                final_content_hash=text_hash(approved_content) if approved_content else None,
                change_summary=command.change_summary,
                reusable_as_example=command.reusable_as_example,
            )
            await uow.review_packages.save(package)
            await uow.review_records.add(record)
            event_payload: dict[str, object] = {
                "reviewPackageId": str(package.id),
                "reviewRecordId": str(record.id),
                "decision": command.decision.value,
                "status": package.status.value,
            }
            await uow.audit_events.add(
                AuditEvent(
                    id=uuid4(),
                    aggregate_type="review_package",
                    aggregate_id=package.id,
                    event_type="review_package_reviewed",
                    actor_id=command.actor_id,
                    payload=event_payload,
                    correlation_id=command.correlation_id,
                )
            )
            await uow.outbox_events.add(
                OutboxEvent(
                    id=uuid4(),
                    event_type="ReviewPackageReviewed",
                    aggregate_type="review_package",
                    aggregate_id=package.id,
                    payload=event_payload,
                    correlation_id=command.correlation_id,
                )
            )
            await uow.idempotency.add(
                IdempotencyRecord(
                    id=uuid4(),
                    operation=self.OPERATION,
                    idempotency_key=command.idempotency_key,
                    request_hash=digest,
                    response_payload={
                        "reviewPackageId": str(package.id),
                        "reviewRecordId": str(record.id),
                        "status": package.status.value,
                    },
                )
            )
            await uow.commit()
        return ReviewRecordedResult(
            review_package_id=package.id,
            review_record_id=record.id,
            status=package.status.value,
        )


class QueueCommunicationHandler:
    OPERATION = "queue_approved_communication"

    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def execute(
        self, command: QueueCommunicationCommand
    ) -> CommunicationQueuedResult:
        payload = {"reviewPackageId": str(command.review_package_id)}
        digest = request_hash(payload)
        async with self._uow_factory() as uow:
            await uow.lock_idempotency(operation=self.OPERATION, key=command.idempotency_key)
            replay = require_matching_replay(
                await uow.idempotency.get(
                    operation=self.OPERATION, key=command.idempotency_key
                ),
                expected_hash=digest,
                idempotency_key=command.idempotency_key,
            )
            if replay is not None:
                return CommunicationQueuedResult(
                    communication_id=replay_uuid(replay, "communicationId"),
                    status=str(replay.response_payload["status"]),
                    idempotent_replay=True,
                )
            package = await uow.review_packages.get_for_update(command.review_package_id)
            if package is None:
                raise EntityNotFoundError("Review package was not found.")
            record = await uow.review_records.get_latest_approved(package.id)
            if record is None:
                raise EntityNotFoundError(
                    "No approved review record exists for this package."
                )
            existing_communication = await uow.communications.get_by_review_record(record.id)
            if existing_communication is not None:
                await uow.idempotency.add(
                    IdempotencyRecord(
                        id=uuid4(),
                        operation=self.OPERATION,
                        idempotency_key=command.idempotency_key,
                        request_hash=digest,
                        response_payload={
                            "communicationId": str(existing_communication.id),
                            "status": existing_communication.status.value,
                        },
                    )
                )
                await uow.commit()
                return CommunicationQueuedResult(
                    communication_id=existing_communication.id,
                    status=existing_communication.status.value,
                    idempotent_replay=True,
                )
            communication = Communication.create_from_approved_review(
                package=package,
                record=record,
                actor_id=command.actor_id,
                correlation_id=command.correlation_id,
            )
            await uow.communications.add(communication)
            event_payload: dict[str, object] = {
                "communicationId": str(communication.id),
                "reviewPackageId": str(package.id),
                "reviewRecordId": str(record.id),
                "channel": communication.channel.value,
            }
            await uow.audit_events.add(
                AuditEvent(
                    id=uuid4(),
                    aggregate_type="communication",
                    aggregate_id=communication.id,
                    event_type="approved_communication_queued",
                    actor_id=command.actor_id,
                    payload=event_payload,
                    correlation_id=command.correlation_id,
                )
            )
            await uow.outbox_events.add(
                OutboxEvent(
                    id=uuid4(),
                    event_type="CommunicationSendRequested",
                    aggregate_type="communication",
                    aggregate_id=communication.id,
                    payload=event_payload,
                    correlation_id=command.correlation_id,
                )
            )
            await uow.idempotency.add(
                IdempotencyRecord(
                    id=uuid4(),
                    operation=self.OPERATION,
                    idempotency_key=command.idempotency_key,
                    request_hash=digest,
                    response_payload={
                        "communicationId": str(communication.id),
                        "status": communication.status.value,
                    },
                )
            )
            await uow.commit()
        return CommunicationQueuedResult(
            communication_id=communication.id,
            status=communication.status.value,
        )
