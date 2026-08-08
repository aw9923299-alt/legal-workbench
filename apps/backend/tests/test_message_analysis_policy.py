from uuid import UUID

import pytest

from legal_workbench.application.message_analysis_policy import MessageAnalysisPolicy
from legal_workbench.domain.entities import IntegrationScope
from legal_workbench.domain.enums import (
    IntegrationIdentityType,
    IntegrationScopeType,
)


def scope(*, scope_type: IntegrationScopeType, high_value: bool = False) -> IntegrationScope:
    return IntegrationScope(
        id=UUID("00000000-0000-0000-0000-000000000501"),
        provider="feishu",
        external_scope_id="oc_policy",
        display_name="Policy scope",
        identity_type=IntegrationIdentityType.USER,
        scope_type=scope_type,
        authorization_id=UUID("00000000-0000-0000-0000-000000000502"),
        high_value_legal=high_value,
    )


@pytest.mark.parametrize(
    ("raw_message", "expected_reason"),
    [
        ({"mentions": [{"id": {"open_id": "ou_self"}}]}, "mentioned_self"),
        ({"parent_sender_id": "ou_self"}, "replied_to_self"),
        ({"body": {"content": '{"text":"请在明天下午完成合同审查"}'}}, "task_or_deadline"),
    ],
)
def test_policy_analyzes_direct_legal_signals(
    raw_message: dict[str, object], expected_reason: str
) -> None:
    decision = MessageAnalysisPolicy().decide(
        raw_message=raw_message,
        scope=scope(scope_type=IntegrationScopeType.GROUP),
        self_open_id="ou_self",
    )

    assert decision.disposition == "analyze"
    assert expected_reason in decision.reasons


def test_policy_analyzes_p2p_and_high_value_groups_but_stores_ordinary_groups() -> None:
    policy = MessageAnalysisPolicy()
    p2p = policy.decide(
        raw_message={"body": {"content": '{"text":"你好"}'}},
        scope=scope(scope_type=IntegrationScopeType.P2P),
        self_open_id="ou_self",
    )
    high_value = policy.decide(
        raw_message={"body": {"content": '{"text":"普通同步信息"}'}},
        scope=scope(scope_type=IntegrationScopeType.GROUP, high_value=True),
        self_open_id="ou_self",
    )
    ordinary = policy.decide(
        raw_message={"body": {"content": '{"text":"普通同步信息"}'}},
        scope=scope(scope_type=IntegrationScopeType.GROUP),
        self_open_id="ou_self",
    )

    assert p2p.disposition == "analyze"
    assert high_value.disposition == "analyze"
    assert ordinary.disposition == "store_only"
    assert ordinary.reasons == ("no_priority_signal",)


def test_ingestion_schema_persists_policy_decision_without_invoking_codex() -> None:
    from legal_workbench.infrastructure.database import Base

    table = Base.metadata.tables["feishu_messages"]
    assert {"analysis_disposition", "analysis_policy_version", "analysis_reasons"} <= set(
        table.c.keys()
    )
