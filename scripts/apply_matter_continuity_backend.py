from __future__ import annotations

from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected one replacement, found {count}: {old[:120]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


# Repository reads: keep continuity evidence in the existing PostgreSQL UoW.
replace_once(
    "apps/backend/src/legal_workbench/infrastructure/repositories.py",
    """    async def append_revision(self, revision: CandidateRevision) -> None:\n""",
    """    async def list_confirmed_matter_links_for_messages(\n        self, message_ids: Sequence[UUID]\n    ) -> Sequence[tuple[UUID, UUID]]:\n        if not message_ids:\n            return []\n        statement = (\n            select(\n                MessageCandidateModel.feishu_message_id,\n                CandidateMatterLinkModel.matter_id,\n            )\n            .join(\n                CandidateMatterLinkModel,\n                CandidateMatterLinkModel.candidate_id == MessageCandidateModel.id,\n            )\n            .where(\n                MessageCandidateModel.feishu_message_id.in_(list(message_ids)),\n                CandidateMatterLinkModel.confirmed_by.is_not(None),\n            )\n            .distinct()\n            .order_by(\n                MessageCandidateModel.feishu_message_id,\n                CandidateMatterLinkModel.matter_id,\n            )\n        )\n        rows = (await self._session.execute(statement)).all()\n        return [\n            (message_id, matter_id)\n            for message_id, matter_id in rows\n            if message_id is not None\n        ]\n\n    async def append_revision(self, revision: CandidateRevision) -> None:\n""",
)

replace_once(
    "apps/backend/src/legal_workbench/infrastructure/repositories.py",
    """    async def get_by_review_record(self, review_record_id: UUID) -> Communication | None:\n        statement = select(CommunicationModel).where(\n            CommunicationModel.review_record_id == review_record_id\n        )\n        model = (await self._session.execute(statement)).scalar_one_or_none()\n        return None if model is None else self._to_domain(model)\n\n    async def list(\n        self, *, status: CommunicationStatus | None, limit: int\n    ) -> Sequence[Communication]:\n""",
    """    async def get_by_review_record(self, review_record_id: UUID) -> Communication | None:\n        statement = select(CommunicationModel).where(\n            CommunicationModel.review_record_id == review_record_id\n        )\n        model = (await self._session.execute(statement)).scalar_one_or_none()\n        return None if model is None else self._to_domain(model)\n\n    async def list_sent_by_external_message_ids(\n        self, external_message_ids: Sequence[str]\n    ) -> Sequence[Communication]:\n        if not external_message_ids:\n            return []\n        statement = (\n            select(CommunicationModel)\n            .where(\n                CommunicationModel.status == CommunicationStatus.SENT,\n                CommunicationModel.external_message_id.in_(list(external_message_ids)),\n            )\n            .order_by(\n                CommunicationModel.sent_at.desc().nullslast(),\n                CommunicationModel.id,\n            )\n        )\n        models = (await self._session.execute(statement)).scalars().all()\n        return [self._to_domain(model) for model in models]\n\n    async def list(\n        self, *, status: CommunicationStatus | None, limit: int\n    ) -> Sequence[Communication]:\n""",
)

# Immutable snapshot: inject resolver explicitly, include evidence in content/hash.
replace_once(
    "apps/backend/src/legal_workbench/application/context_snapshots.py",
    """from legal_workbench.application.ports import UnitOfWorkFactory\n""",
    """from legal_workbench.application.matter_continuity import MatterContinuityResolver\nfrom legal_workbench.application.ports import UnitOfWorkFactory\n""",
)
replace_once(
    "apps/backend/src/legal_workbench/application/context_snapshots.py",
    """        selection_policy_version: str = \"thread-v2\",\n        now: Callable[[], datetime] | None = None,\n    ) -> None:\n""",
    """        selection_policy_version: str = \"thread-v2\",\n        matter_continuity_resolver: MatterContinuityResolver | None = None,\n        now: Callable[[], datetime] | None = None,\n    ) -> None:\n""",
)
replace_once(
    "apps/backend/src/legal_workbench/application/context_snapshots.py",
    """        self._selection_policy_version = selection_policy_version\n        self._now = now or (lambda: datetime.now(UTC))\n""",
    """        self._selection_policy_version = selection_policy_version\n        self._matter_continuity_resolver = matter_continuity_resolver\n        self._now = now or (lambda: datetime.now(UTC))\n""",
)
replace_once(
    "apps/backend/src/legal_workbench/application/context_snapshots.py",
    """            selected = self._select_messages(current, available)\n            all_attachment_ids = _attachment_ids(selected)\n""",
    """            selected = self._select_messages(current, available)\n            continuity_proposals = (\n                await self._matter_continuity_resolver.resolve(\n                    uow, current=current, context_messages=selected\n                )\n                if self._matter_continuity_resolver is not None\n                else []\n            )\n            continuity_payload = [value.to_payload() for value in continuity_proposals]\n            relevant_matter_ids = [str(value.matter_id) for value in continuity_proposals]\n            all_attachment_ids = _attachment_ids(selected)\n""",
)
replace_once(
    "apps/backend/src/legal_workbench/application/context_snapshots.py",
    """            content, content_metrics = self._build_content(\n                selected,\n                current_message_id=current.message_id,\n                allowed_attachment_ids=set(attachment_ids),\n            )\n""",
    """            content, content_metrics = self._build_content(\n                selected,\n                current_message_id=current.message_id,\n                allowed_attachment_ids=set(attachment_ids),\n            )\n            content[\"matterContinuityProposals\"] = continuity_payload\n""",
)
replace_once(
    "apps/backend/src/legal_workbench/application/context_snapshots.py",
    """                \"messageIds\": [message.message_id for message in selected],\n                \"participantIds\": participants,\n""",
    """                \"messageIds\": [message.message_id for message in selected],\n                \"relevantMatterIds\": relevant_matter_ids,\n                \"participantIds\": participants,\n""",
)
replace_once(
    "apps/backend/src/legal_workbench/application/context_snapshots.py",
    """                relevant_matter_ids=[],\n""",
    """                relevant_matter_ids=relevant_matter_ids,\n""",
)

# Canonical worker explicitly enables continuity for real message processing.
replace_once(
    "apps/backend/src/legal_workbench/workers/tasks.py",
    """from legal_workbench.application.legal_context import LegalContextBuilder\n""",
    """from legal_workbench.application.legal_context import LegalContextBuilder\nfrom legal_workbench.application.matter_continuity import MatterContinuityResolver\n""",
)
replace_once(
    "apps/backend/src/legal_workbench/workers/tasks.py",
    """            selection_policy_version=settings.context_selection_policy_version,\n        ),\n        runs_root=settings.codex_runs_root,\n""",
    """            selection_policy_version=settings.context_selection_policy_version,\n            matter_continuity_resolver=MatterContinuityResolver(),\n        ),\n        runs_root=settings.codex_runs_root,\n""",
)

# Canonical Candidate persistence copies proposals from the immutable snapshot.
replace_once(
    "apps/backend/src/legal_workbench/application/message_analysis.py",
    """            message = await uow.feishu.get_message_for_update(run.feishu_message_id)\n            if message is None:\n                raise RuntimeError(\"FeishuMessage disappeared before result persistence.\")\n            await AgentExecutionLeaseService(\n""",
    """            message = await uow.feishu.get_message_for_update(run.feishu_message_id)\n            if message is None:\n                raise RuntimeError(\"FeishuMessage disappeared before result persistence.\")\n            snapshot = await uow.context_snapshots.get(run.context_snapshot_id)\n            if snapshot is None:\n                raise RuntimeError(\"ContextSnapshot disappeared before result persistence.\")\n            related_matter_proposals = self._matter_continuity_proposals(snapshot)\n            await AgentExecutionLeaseService(\n""",
)
replace_once(
    "apps/backend/src/legal_workbench/application/message_analysis.py",
    """                        related_matter_proposals=[],\n""",
    """                        related_matter_proposals=related_matter_proposals,\n""",
)
replace_once(
    "apps/backend/src/legal_workbench/application/message_analysis.py",
    """                        deadline_proposals=[\n                            value.model_dump(by_alias=True, mode=\"json\")\n                            for value in output.deadline_candidates\n                        ],\n                        evidence_refs=self._evidence_refs(output),\n""",
    """                        deadline_proposals=[\n                            value.model_dump(by_alias=True, mode=\"json\")\n                            for value in output.deadline_candidates\n                        ],\n                        related_matter_proposals=related_matter_proposals,\n                        evidence_refs=self._evidence_refs(output),\n""",
)
replace_once(
    "apps/backend/src/legal_workbench/application/message_analysis.py",
    """            revision_candidate_id = existing.id if existing is not None else candidate_id\n""",
    """            if candidate_id is not None and related_matter_proposals:\n                await uow.audit_events.add(\n                    AuditEvent(\n                        id=uuid4(),\n                        aggregate_type=\"feishu_message\",\n                        aggregate_id=message.id,\n                        event_type=\"matter_continuity_candidates_materialized\",\n                        actor_id=command.actor_id,\n                        actor_source=command.actor_source,\n                        payload={\n                            \"agentRunId\": str(run.id),\n                            \"contextSnapshotId\": str(snapshot.id),\n                            \"candidateId\": str(candidate_id),\n                            \"matterIds\": [\n                                str(value.get(\"matterId\"))\n                                for value in related_matter_proposals\n                                if value.get(\"matterId\")\n                            ],\n                            \"signals\": {\n                                str(value.get(\"matterId\")): value.get(\"signals\", [])\n                                for value in related_matter_proposals\n                                if value.get(\"matterId\")\n                            },\n                        },\n                        correlation_id=command.correlation_id,\n                    )\n                )\n            revision_candidate_id = existing.id if existing is not None else candidate_id\n""",
)
replace_once(
    "apps/backend/src/legal_workbench/application/message_analysis.py",
    """    @staticmethod\n    async def _append_candidate_revision(\n""",
    """    @staticmethod\n    def _matter_continuity_proposals(\n        snapshot: ContextSnapshot,\n    ) -> list[dict[str, object]]:\n        raw = snapshot.content.get(\"matterContinuityProposals\", [])\n        if not isinstance(raw, list):\n            return []\n        return [\n            dict(value)\n            for value in raw\n            if isinstance(value, dict) and value.get(\"matterId\")\n        ]\n\n    @staticmethod\n    async def _append_candidate_revision(\n""",
)

# The new behavior tests explicitly configure the resolver, just like production.
replace_once(
    "apps/backend/tests/test_matter_continuity.py",
    """from legal_workbench.application.context_snapshots import ContextSnapshotBuilder\n""",
    """from legal_workbench.application.context_snapshots import ContextSnapshotBuilder\nfrom legal_workbench.application.matter_continuity import MatterContinuityResolver\n""",
)
text_path = Path("apps/backend/tests/test_matter_continuity.py")
text = text_path.read_text(encoding="utf-8")
needle = """        max_messages=10,\n        max_text_characters=5000,\n    ).build_for_feishu_message(current.id)\n"""
replacement = """        max_messages=10,\n        max_text_characters=5000,\n        matter_continuity_resolver=MatterContinuityResolver(),\n    ).build_for_feishu_message(current.id)\n"""
if text.count(needle) != 3:
    raise RuntimeError("expected three Matter continuity builder test call sites")
text_path.write_text(text.replace(needle, replacement), encoding="utf-8")
