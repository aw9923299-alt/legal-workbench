from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from legal_workbench.agents.message_judgement import (
    MessageJudgementInput,
    MessageJudgementResult,
    candidate_requires_manual_review,
    should_create_candidate,
    validate_confirmed_fact_sources,
)
from legal_workbench.domain.entities import AgentDefinition, AgentRun, FeishuMessage
from legal_workbench.domain.enums import (
    AgentDefinitionStatus,
    AgentRunStatus,
    FeishuMessageStatus,
)
from legal_workbench.domain.errors import DomainValidationError, InvalidStateTransitionError


def make_definition() -> AgentDefinition:
    return AgentDefinition(
        id=uuid4(),
        key="message_judgement",
        name="消息研判",
        version="1.0.0",
        description="判断飞书消息是否形成法务候选。",
        status=AgentDefinitionStatus.ACTIVE,
        prompt_template="Return strict JSON.",
        input_schema={"type": "object"},
        output_schema={"type": "object"},
        allowed_tools=[],
        allowed_knowledge_scopes=[],
        timeout_seconds=60,
        max_retries=2,
        requires_human_review=True,
    )


def make_run(*, status: AgentRunStatus = AgentRunStatus.QUEUED) -> AgentRun:
    return AgentRun(
        id=uuid4(),
        agent_definition_id=make_definition().id,
        context_snapshot_id=uuid4(),
        status=status,
        objective="Analyse one authorized Feishu message.",
        prompt_snapshot="Return strict JSON.",
        working_directory="/tmp/test-run",
        attempt_number=1,
        max_attempts=3,
        correlation_id="corr-domain",
        created_by="system",
    )


def valid_result(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "legalRelevance": "relevant",
        "messageRole": "new_request",
        "actionability": "create_candidate",
        "suggestedTitle": "审核新供应商合同",
        "categoryCandidates": [
            {"category": "contract", "confidence": 0.9, "reason": "消息明确提到合同审核"}
        ],
        "deadlineCandidates": [],
        "confirmedFacts": [{"statement": "请求审核合同", "sourceMessageId": "om_current"}],
        "inferredFacts": [],
        "missingInformation": ["合同附件尚未提供"],
        "reasons": ["存在明确法务行动要求"],
        "confidence": 0.8,
    }
    payload.update(overrides)
    return payload


def valid_input(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "runId": str(uuid4()),
        "agentDefinition": {"key": "message_judgement", "version": "1.0.0"},
        "objective": "Analyse the authorized message.",
        "contextSnapshot": {
            "id": str(uuid4()),
            "contentHash": "a" * 64,
            "messageIds": ["om_current"],
            "participantIds": ["ou_sender"],
            "attachmentIds": [],
            "includedSegments": [],
            "excludedSegments": [],
            "builderVersion": "2.0.0",
            "selectionPolicyVersion": "thread-v2",
            "currentMessageVersion": 1,
            "attachmentVersionHash": "b" * 64,
            "truncated": False,
            "truncationReason": None,
            "originalSize": 0,
            "includedSize": 0,
            "threadMetadata": {},
            "content": {"messages": []},
        },
        "constraints": {
            "networkAccess": False,
            "databaseAccess": False,
            "repositoryAccess": False,
            "shellWriteAccess": False,
            "allowedMessageIds": ["om_current"],
            "allowedAttachmentIds": [],
        },
    }
    payload.update(overrides)
    return payload


def test_agent_run_rejects_skipping_required_states() -> None:
    run = make_run()

    with pytest.raises(InvalidStateTransitionError):
        run.transition_to(AgentRunStatus.COMPLETED)


def test_agent_run_tracks_heartbeat_and_optimistic_version() -> None:
    run = make_run()
    now = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)

    run.transition_to(AgentRunStatus.PREPARING, now=now)
    run.transition_to(AgentRunStatus.RUNNING, now=now)
    run.heartbeat(now=now)

    assert run.started_at == now
    assert run.heartbeat_at == now
    assert run.version == 4


def test_message_judgement_forbids_schema_extensions() -> None:
    with pytest.raises(ValidationError, match="extra_forbidden"):
        MessageJudgementResult.model_validate(valid_result(unexpected="unsafe"))


def test_message_judgement_input_contract_accepts_runtime_payload_and_forbids_extensions() -> None:
    assert MessageJudgementInput.model_validate(valid_input()).run_id

    with pytest.raises(ValidationError, match="extra_forbidden"):
        MessageJudgementInput.model_validate(valid_input(unexpected="unsafe"))


def test_confirmed_facts_must_reference_authorized_messages() -> None:
    result = MessageJudgementResult.model_validate(valid_result())

    with pytest.raises(DomainValidationError, match="unauthorized source"):
        validate_confirmed_fact_sources(result, {"om_parent"})


def test_attachment_fact_must_reference_an_exact_authorized_segment() -> None:
    citation = {
        "attachmentId": "attachment-1",
        "fileName": "合同.pdf",
        "pageNumber": 2,
        "paragraphNumber": 3,
        "contentHash": "c" * 64,
    }
    result = MessageJudgementResult.model_validate(
        valid_result(
            confirmedFacts=[
                {
                    "statement": "合同期限一年",
                    "attachmentCitation": citation,
                }
            ]
        )
    )

    validate_confirmed_fact_sources(
        result,
        {"om_current"},
        {("attachment-1", "合同.pdf", 2, 3, "c" * 64)},
    )
    with pytest.raises(DomainValidationError, match="unauthorized attachment segment"):
        validate_confirmed_fact_sources(result, {"om_current"}, set())


@pytest.mark.parametrize(
    "fact",
    [
        {"statement": "没有引用"},
        {
            "statement": "重复引用",
            "sourceMessageId": "om_current",
            "attachmentCitation": {
                "attachmentId": "attachment-1",
                "fileName": "合同.pdf",
                "pageNumber": 2,
                "paragraphNumber": 3,
                "contentHash": "c" * 64,
            },
        },
    ],
)
def test_confirmed_fact_requires_exactly_one_evidence_source(
    fact: dict[str, object],
) -> None:
    with pytest.raises(ValidationError, match="exactly one evidence source"):
        MessageJudgementResult.model_validate(valid_result(confirmedFacts=[fact]))


def test_irrelevant_message_never_creates_candidate() -> None:
    result = MessageJudgementResult.model_validate(
        valid_result(legalRelevance="irrelevant", actionability="ignore")
    )

    assert should_create_candidate(result) is False


def test_low_confidence_candidate_requires_manual_review() -> None:
    result = MessageJudgementResult.model_validate(valid_result(confidence=0.4))

    assert should_create_candidate(result) is True
    assert candidate_requires_manual_review(result, threshold=0.75) is True


def test_feishu_message_failure_transition_requires_reason() -> None:
    message = FeishuMessage(
        id=uuid4(),
        event_id=uuid4(),
        tenant_key="tenant",
        message_id="om_current",
        chat_id="oc_chat",
        thread_id=None,
        root_id=None,
        parent_id=None,
        sender_id="ou_sender",
        sender_type="user",
        message_type="text",
        content={"text": "请审核合同"},
        mentions=[],
        create_time=None,
        update_time=None,
        raw_message={},
    )

    message.transition_to(FeishuMessageStatus.QUEUED_FOR_ANALYSIS)
    with pytest.raises(DomainValidationError, match="failure code"):
        message.transition_to(FeishuMessageStatus.ANALYSIS_FAILED)
