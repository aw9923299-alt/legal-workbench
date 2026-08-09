from __future__ import annotations

import json
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from legal_workbench.agents.codex_cli import CodexCliRuntime
from legal_workbench.agents.definitions import build_legal_agent_definitions
from legal_workbench.agents.legal_contracts import ContractReviewProduct
from legal_workbench.agents.runtime import AgentExecutionContext
from legal_workbench.domain.entities import AgentRun, ContextSnapshot
from legal_workbench.domain.enums import AgentRunRole, AgentRunStatus


def _contract_output() -> dict[str, object]:
    return {
        "executiveSummary": "第8.2条责任范围需要收窄。",
        "facts": [{"fact": "第8.2条约定乙方承担全部责任。", "sourceRefs": ["ctx:segment:s-1"]}],
        "issues": ["责任范围是否无上限"],
        "legalBasis": [
            {
                "proposition": "合同责任应结合约定与适用法律判断。",
                "sourceRefs": ["knowledge:chunk:k-1"],
                "jurisdiction": "CN",
                "effectiveDate": date(2021, 1, 1).isoformat(),
            }
        ],
        "analysis": [
            {
                "conclusion": "现有表述可能形成无上限责任。",
                "supportRefs": ["ctx:segment:s-1", "knowledge:chunk:k-1"],
            }
        ],
        "risks": [{"description": "责任无上限", "severity": "high", "likelihood": "possible"}],
        "recommendedActions": ["将责任上限修改为年度服务费"],
        "missingInformation": [],
        "assumptions": [],
        "draftResponse": "建议将第8.2条责任上限调整为年度服务费。",
        "confidence": 0.84,
        "citations": [
            {
                "sourceRef": "knowledge:chunk:k-1",
                "title": "非敏感法规测试资料",
                "sourceType": "knowledge_document",
                "locator": "第一条",
                "contentHash": None,
                "internalPrecedent": False,
            }
        ],
        "contractSummary": "虚构渠道合作合同",
        "parties": ["甲方", "乙方"],
        "commercialTerms": ["按月支付服务费"],
        "clauseRisks": [
            {
                "clauseLocator": "第8.2条",
                "clauseText": "乙方承担全部责任",
                "risk": "责任范围无上限",
                "severity": "high",
                "sourceRefs": ["ctx:segment:s-1"],
            }
        ],
        "missingTerms": ["责任上限"],
        "proposedChanges": ["增加年度服务费责任上限"],
        "fallbackPositions": ["排除间接损失"],
        "negotiationPoints": ["责任上限"],
    }


@pytest.mark.asyncio
async def test_runtime_validates_contract_review_with_registered_schema(tmp_path: Path) -> None:
    output = _contract_output()
    script = tmp_path / "fake-professional-codex.py"
    script.write_text(
        "import pathlib, sys\n"
        "prompt = sys.stdin.read()\n"
        "if 'authorized_context_json' not in prompt or 'contract_review' not in prompt:\n"
        "    raise SystemExit(9)\n"
        "target = pathlib.Path(sys.argv[sys.argv.index('--output-last-message') + 1])\n"
        f"target.write_text({json.dumps(json.dumps(output))}, encoding='utf-8')\n",
        encoding="utf-8",
    )
    definition = build_legal_agent_definitions()["contract_review"]
    snapshot = ContextSnapshot(
        id=uuid4(),
        source_type="legal_matter",
        source_id="matter-fixture",
        source_ids=["s-1", "k-1"],
        message_ids=[],
        file_ids=[],
        relevant_matter_ids=[],
        participant_ids=[],
        permission_snapshot={},
        generated_at=datetime.now(UTC),
        content_hash="a" * 64,
        content={"contractSegments": [{"sourceRef": "ctx:segment:s-1"}]},
    )
    run = AgentRun(
        id=uuid4(),
        agent_definition_id=definition.id,
        context_snapshot_id=snapshot.id,
        status=AgentRunStatus.QUEUED,
        objective="定位具体合同条款风险",
        prompt_snapshot=definition.prompt_template,
        working_directory=str(tmp_path / "unused"),
        attempt_number=1,
        max_attempts=2,
        correlation_id="corr-professional",
        created_by="test",
        run_role=AgentRunRole.SPECIALIST,
    )
    context = AgentExecutionContext(
        snapshot=snapshot,
        input_payload={
            "runId": str(run.id),
            "phase": "specialist",
            "objective": run.objective,
            "matterId": None,
            "workItemId": None,
            "authorizedContext": snapshot.content,
            "authorizedSourceRefs": ["ctx:segment:s-1", "knowledge:chunk:k-1"],
            "upstreamOutputs": {},
            "constraints": {
                "networkAccess": False,
                "databaseAccess": False,
                "repositoryAccess": False,
                "shellAccess": False,
            },
        },
        authorized_source_refs=frozenset({"ctx:segment:s-1", "knowledge:chunk:k-1"}),
    )
    runtime = CodexCliRuntime(
        runs_root=tmp_path / "runs",
        command=[sys.executable, str(script)],
    )

    result = await runtime.execute(definition, run, context)

    assert isinstance(result.output, ContractReviewProduct)
    assert result.output.clause_risks[0].clause_locator == "第8.2条"
    assert run.input_payload["phase"] == "specialist"
