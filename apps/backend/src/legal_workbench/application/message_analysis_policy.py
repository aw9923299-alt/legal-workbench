from __future__ import annotations

import json
import re
from dataclasses import dataclass

from legal_workbench.domain.entities import IntegrationScope
from legal_workbench.domain.enums import IntegrationScopeType

POLICY_VERSION = "feishu-personal-analysis-v1"
_TASK_OR_DEADLINE = re.compile(
    r"(请|麻烦|需要|务必|完成|处理|审核|审查|起草|回复|提交|截止|到期|"
    r"今天|明天|本周|下周|\d{1,2}[月/-]\d{1,2}[日号]?|"
    r"please|review|draft|reply|submit|deadline|due)",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class MessageAnalysisDecision:
    disposition: str
    reasons: tuple[str, ...]
    policy_version: str = POLICY_VERSION


def _message_text(raw_message: dict[str, object]) -> str:
    body = raw_message.get("body")
    content: object = body.get("content") if isinstance(body, dict) else raw_message.get("content")
    if isinstance(content, str):
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            return content
        if isinstance(parsed, dict):
            return str(parsed.get("text") or parsed)
        return str(parsed)
    return str(content or "")


def _mentions_self(raw_message: dict[str, object], self_open_id: str) -> bool:
    mentions = raw_message.get("mentions")
    if not isinstance(mentions, list) or not self_open_id:
        return False
    for mention in mentions:
        if not isinstance(mention, dict):
            continue
        identity = mention.get("id")
        if isinstance(identity, dict) and self_open_id in identity.values():
            return True
        if self_open_id in {
            str(mention.get("open_id") or ""),
            str(mention.get("id") or ""),
        }:
            return True
    return False


class MessageAnalysisPolicy:
    def decide(
        self,
        *,
        raw_message: dict[str, object],
        scope: IntegrationScope,
        self_open_id: str,
    ) -> MessageAnalysisDecision:
        reasons: list[str] = []
        if scope.scope_type == IntegrationScopeType.P2P:
            reasons.append("p2p")
        if _mentions_self(raw_message, self_open_id):
            reasons.append("mentioned_self")
        if self_open_id and str(raw_message.get("parent_sender_id") or "") == self_open_id:
            reasons.append("replied_to_self")
        if _TASK_OR_DEADLINE.search(_message_text(raw_message)):
            reasons.append("task_or_deadline")
        if scope.high_value_legal:
            reasons.append("high_value_legal_scope")
        if not reasons:
            return MessageAnalysisDecision(
                disposition="store_only",
                reasons=("no_priority_signal",),
            )
        return MessageAnalysisDecision(
            disposition="analyze",
            reasons=tuple(dict.fromkeys(reasons)),
        )
