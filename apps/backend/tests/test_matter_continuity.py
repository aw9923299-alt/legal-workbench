from __future__ import annotations

from datetime import UTC, datetime
from types import TracebackType
from uuid import UUID, uuid4

import pytest

from legal_workbench.application.context_snapshots import ContextSnapshotBuilder
from legal_workbench.domain.entities import (
    Communication,
    ContextSnapshot,
    FeishuMessage,
    LegalMatter,
)
from legal_workbench.domain.enums import (
    BusinessImpact,
    CommunicationChannel,
    CommunicationStatus,
    Confidentiality,
    LegalRisk,
    MatterCategory,
)


def make_message(
    external_id: str,
    *,
    thread_id: str | None = None,
    root_id: str | None = None,
    parent_id: str | None = None,
) -> FeishuMessage:
    return FeishuMessage(
        id=uuid4(),
        event_id=uuid4(),
        tenant_key="tenant",
        message_id=external_id,
        chat_id="oc_chat",
        thread_id=thread_id,
        root_id=root_id,
        parent_id=parent_id,
        sender_id="ou_business",
        sender_type="user",
        message_type="text",
        content={"text": external_id},
        mentions=[],
        create_time=datetime.now(UTC),
        update_time=None,
        raw_message={},
    )


def make_matter(title: str = "历史合同审核") -> LegalMatter:
    return LegalMatter.create(
        title=title,
        primary_category=MatterCategory.CONTRACT,
        secondary_categories=[],
        owner_id="local-legal-user",
        legal_risk=LegalRisk.MEDIUM,
        business_impact=BusinessImpact.GENERAL,
        confidentiality=Confidentiality.INTERNAL,
        requester_ids=[],
        summary=None,
        objective=None,
    )


class FakeFeishuRepository:
    def __init__(self, current: FeishuMessage, context: list[FeishuMessage]) -> None:
        self.current = current
        self.context = context

    async def get_message_by_id(self, message_id: UUID) -> FeishuMessage | None:
        return self.current if self.current.id == message_id else None

    async def list_context_messages(
        self, message: FeishuMessage, *, limit: int
    ) -> list[FeishuMessage]:
        assert message.id == self.current.id
        return self.context[:limit]

    async def list_attachments(self, message_id: UUID) -> tuple[()]:
        del message_id
        return ()


class FakeDocumentRepository:
    async def list_latest_segments(self, attachment_ids: list[UUID]) -> tuple[()]:
        del attachment_ids
        return ()

    async def list_latest_feishu_segments_for_messages(
        self, message_ids: list[UUID]
    ) -> tuple[()]:
        del message_ids
        return ()


class FakeSnapshotRepository:
    def __init__(self) -> None:
        self.values: list[ContextSnapshot] = []

    async def find_by_source_hash(
        self, *, source_type: str, source_id: str, content_hash: str
    ) -> ContextSnapshot | None:
        return next(
            (
                value
                for value in self.values
                if value.source_type == source_type
                and value.source_id == source_id
                and value.content_hash == content_hash
            ),
            None,
        )

    async def add(self, snapshot: ContextSnapshot) -> None:
        self.values.append(snapshot)


class FakeCandidateRepository:
    def __init__(self, links: list[tuple[UUID, UUID]] | None = None) -> None:
        self.links = links or []

    async def list_confirmed_matter_links_for_messages(
        self, message_ids: list[UUID]
    ) -> list[tuple[UUID, UUID]]:
        allowed = set(message_ids)
        return [value for value in self.links if value[0] in allowed]


class FakeCommunicationRepository:
    def __init__(self, values: list[Communication] | None = None) -> None:
        self.values = values or []

    async def list_sent_by_external_message_ids(
        self, external_message_ids: list[str]
    ) -> list[Communication]:
        allowed = set(external_message_ids)
        return [
            value
            for value in self.values
            if value.external_message_id is not None
            and value.external_message_id in allowed
            and value.status == CommunicationStatus.SENT
        ]


class FakeMatterRepository:
    def __init__(self, values: list[LegalMatter]) -> None:
        self.values = {value.id: value for value in values}

    async def get(self, matter_id: UUID) -> LegalMatter | None:
        return self.values.get(matter_id)


class FakeUnitOfWork:
    def __init__(
        self,
        *,
        current: FeishuMessage,
        context: list[FeishuMessage],
        matters: list[LegalMatter],
        links: list[tuple[UUID, UUID]] | None = None,
        communications: list[Communication] | None = None,
    ) -> None:
        self.feishu = FakeFeishuRepository(current, context)
        self.context_snapshots = FakeSnapshotRepository()
        self.documents = FakeDocumentRepository()
        self.candidates = FakeCandidateRepository(links)
        self.communications = FakeCommunicationRepository(communications)
        self.matters = FakeMatterRepository(matters)
        self.commits = 0

    async def __aenter__(self) -> FakeUnitOfWork:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None

    async def lock_idempotency(self, *, operation: str, key: str) -> None:
        del operation, key

    async def commit(self) -> None:
        self.commits += 1


def make_sent_communication(matter: LegalMatter, external_message_id: str) -> Communication:
    return Communication(
        id=uuid4(),
        matter_id=matter.id,
        work_item_id=None,
        review_package_id=uuid4(),
        review_record_id=uuid4(),
        channel=CommunicationChannel.FEISHU,
        target={"replyToMessageId": "om_source"},
        content="请补充材料",
        content_hash="a" * 64,
        status=CommunicationStatus.SENT,
        requested_by="local-legal-user",
        correlation_id="corr-continuity",
        external_message_id=external_message_id,
        sent_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_snapshot_proposes_matter_when_message_replies_to_sent_communication() -> None:
    matter = make_matter()
    outbound_id = "om_outbound"
    current = make_message("om_reply", parent_id=outbound_id)
    communication = make_sent_communication(matter, outbound_id)
    uow = FakeUnitOfWork(
        current=current,
        context=[current],
        matters=[matter],
        communications=[communication],
    )

    snapshot = await ContextSnapshotBuilder(
        lambda: uow,
        max_messages=10,
        max_text_characters=5000,
    ).build_for_feishu_message(current.id)

    assert snapshot.relevant_matter_ids == [str(matter.id)]
    assert snapshot.content["matterContinuityProposals"] == [
        {
            "matterId": str(matter.id),
            "matterNumber": matter.matter_number,
            "title": matter.title,
            "confidence": 1.0,
            "signals": ["reply_to_communication"],
            "evidenceRefs": [
                f"communication:{communication.id}",
                f"message:{outbound_id}",
            ],
        }
    ]


@pytest.mark.asyncio
async def test_snapshot_proposes_matter_from_confirmed_link_in_same_thread() -> None:
    matter = make_matter("同线程争议事项")
    prior = make_message("om_prior", thread_id="omt_case", root_id="om_root")
    current = make_message("om_current", thread_id="omt_case", root_id="om_root")
    uow = FakeUnitOfWork(
        current=current,
        context=[prior, current],
        matters=[matter],
        links=[(prior.id, matter.id)],
    )

    snapshot = await ContextSnapshotBuilder(
        lambda: uow,
        max_messages=10,
        max_text_characters=5000,
    ).build_for_feishu_message(current.id)

    assert snapshot.relevant_matter_ids == [str(matter.id)]
    proposal = snapshot.content["matterContinuityProposals"][0]
    assert proposal["matterId"] == str(matter.id)
    assert proposal["confidence"] == 0.95
    assert proposal["signals"] == ["same_thread_confirmed_link"]
    assert proposal["evidenceRefs"] == [f"message:{prior.message_id}"]


@pytest.mark.asyncio
async def test_snapshot_does_not_use_same_chat_only_as_matter_evidence() -> None:
    matter = make_matter("同群但无关事项")
    prior = make_message("om_unrelated")
    current = make_message("om_current")
    uow = FakeUnitOfWork(
        current=current,
        context=[prior, current],
        matters=[matter],
        links=[(prior.id, matter.id)],
    )

    snapshot = await ContextSnapshotBuilder(
        lambda: uow,
        max_messages=10,
        max_text_characters=5000,
    ).build_for_feishu_message(current.id)

    assert snapshot.relevant_matter_ids == []
    assert snapshot.content["matterContinuityProposals"] == []
