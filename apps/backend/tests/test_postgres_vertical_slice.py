from __future__ import annotations

import os
from uuid import UUID, uuid4

import pytest


@pytest.mark.integration
@pytest.mark.asyncio
async def test_candidate_to_matter_to_work_item_http_slice() -> None:
    if os.getenv("RUN_POSTGRES_INTEGRATION_TESTS") != "1":
        pytest.skip("PostgreSQL integration tests are disabled")

    from httpx import ASGITransport, AsyncClient
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from legal_workbench.api.dependencies import get_uow_factory
    from legal_workbench.infrastructure.unit_of_work import SqlAlchemyUnitOfWorkFactory
    from legal_workbench.main import app

    database_url = os.environ["LEGAL_WORKBENCH_TEST_DATABASE_URL"]
    engine = create_async_engine(database_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    uow_factory = SqlAlchemyUnitOfWorkFactory(session_factory)
    app.dependency_overrides[get_uow_factory] = lambda: uow_factory

    unique_suffix = uuid4().hex
    headers = {
        "Idempotency-Key": f"candidate-{unique_suffix}",
        "X-Correlation-ID": f"correlation-{unique_suffix}",
    }
    candidate_payload = {
        "context": {
            "sourceType": "feishu_group_message",
            "sourceIds": [f"chat-{unique_suffix}"],
            "messageIds": [f"message-{unique_suffix}"],
            "fileIds": [f"file-{unique_suffix}"],
            "relevantMatterIds": [],
            "participantIds": ["business-user-1", "legal-user-1"],
            "permissionSnapshot": {"visibleTo": ["legal-user-1"]},
            "generatedAt": "2026-08-01T09:30:00Z",
            "contentHash": "a" * 64,
        },
        "status": "pending_confirmation",
        "legalRelevance": "relevant",
        "messageRole": "new_request",
        "recommendedAction": "create_matter",
        "confidence": 0.93,
        "titleProposal": "审核品牌合作协议",
        "categoryProposals": [{"category": "contract", "confidence": 0.9}],
        "deadlineProposals": [],
        "relatedMatterProposals": [],
        "evidenceRefs": [f"feishu:message-{unique_suffix}"],
    }

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            session_response = await client.post("/api/v1/auth/local-session")
            assert session_response.status_code == 201, session_response.text
            candidate_response = await client.post(
                "/api/v1/inbox/candidates",
                json=candidate_payload,
                headers=headers,
            )
            assert candidate_response.status_code == 201, candidate_response.text
            candidate_body = candidate_response.json()
            candidate_id = candidate_body["candidateId"]

            replay_response = await client.post(
                "/api/v1/inbox/candidates",
                json=candidate_payload,
                headers=headers,
            )
            assert replay_response.status_code == 200, replay_response.text
            assert replay_response.json()["candidateId"] == candidate_id
            assert replay_response.json()["idempotentReplay"] is True

            second_business_action = await client.post(
                "/api/v1/inbox/candidates",
                json=candidate_payload,
                headers={**headers, "Idempotency-Key": f"candidate-second-{unique_suffix}"},
            )
            assert second_business_action.status_code == 201, second_business_action.text
            assert second_business_action.json()["candidateId"] != candidate_id

            async with engine.connect() as connection:
                snapshot_count = await connection.scalar(
                    text(
                        "SELECT count(*) FROM context_snapshots "
                        "WHERE source_type = :source_type AND source_id = :source_id "
                        "AND content_hash = :content_hash"
                    ),
                    {
                        "source_type": "feishu_group_message",
                        "source_id": f"chat-{unique_suffix}",
                        "content_hash": "a" * 64,
                    },
                )
            assert snapshot_count == 1

            confirmation_headers = {
                **headers,
                "Idempotency-Key": f"confirm-{unique_suffix}",
            }
            confirmation_payload = {
                "candidateVersion": candidate_body["version"],
                "title": "品牌合作协议审核",
                "primaryCategory": "contract",
                "secondaryCategories": ["copy_review"],
                "ownerId": "legal-user-1",
                "requesterIds": ["business-user-1"],
                "legalRisk": "medium",
                "businessImpact": "project",
                "confidentiality": "confidential",
                "summary": "业务希望今日完成协议审核。",
                "objective": "形成修改意见并回复业务。",
                "initialWorkItems": [
                    {
                        "title": "核查合同主体和版本",
                        "ownerId": "legal-user-1",
                        "priority": "high",
                        "prioritySource": "legal_confirmed",
                        "nextAction": "确认签约主体及最终版本。",
                        "priorityReasons": ["今日需要完成审核"],
                        "estimatedMinutes": 20,
                    }
                ],
            }
            matter_response = await client.post(
                f"/api/v1/inbox/candidates/{candidate_id}/confirm-create",
                json=confirmation_payload,
                headers=confirmation_headers,
            )
            assert matter_response.status_code == 201, matter_response.text
            matter_body = matter_response.json()
            matter_id = matter_body["matterId"]
            assert len(matter_body["workItemIds"]) == 1

            matter_detail = await client.get(f"/api/v1/matters/{matter_id}")
            assert matter_detail.status_code == 200, matter_detail.text
            assert matter_detail.json()["matterNumber"].startswith("LW-")

            work_items = await client.get(f"/api/v1/matters/{matter_id}/work-items")
            assert work_items.status_code == 200, work_items.text
            assert [item["title"] for item in work_items.json()] == ["核查合同主体和版本"]

            butler_headers = {
                **headers,
                "Idempotency-Key": f"butler-{unique_suffix}",
            }
            butler_response = await client.post(
                f"/api/v1/matters/{matter_id}/legal-agent-plans",
                json={
                    "objective": "只审查该非敏感合作合同",
                    "specialistOnly": "contract_review",
                    "workItemId": matter_body["workItemIds"][0],
                },
                headers=butler_headers,
            )
            assert butler_response.status_code == 202, butler_response.text
            assert butler_response.json()["status"] == "queued"
            assert UUID(butler_response.json()["contextSnapshotId"])

            butler_replay = await client.post(
                f"/api/v1/matters/{matter_id}/legal-agent-plans",
                json={
                    "objective": "只审查该非敏感合作合同",
                    "specialistOnly": "contract_review",
                    "workItemId": matter_body["workItemIds"][0],
                },
                headers=butler_headers,
            )
            assert butler_replay.status_code == 200, butler_replay.text
            assert butler_replay.json()["idempotentReplay"] is True

            async with engine.connect() as connection:
                butler_events = await connection.scalar(
                    text(
                        "SELECT count(*) FROM outbox_events "
                        "WHERE event_type = 'LegalButlerRequested' "
                        "AND aggregate_id = :matter_id"
                    ),
                    {"matter_id": matter_id},
                )
            assert butler_events == 2
    finally:
        app.dependency_overrides.pop(get_uow_factory, None)
        await engine.dispose()
