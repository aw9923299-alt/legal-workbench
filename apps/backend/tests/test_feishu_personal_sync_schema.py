from datetime import UTC, datetime
from uuid import UUID

from legal_workbench.api.schemas.feishu_user import FeishuPersonalSyncResponse


def test_personal_sync_api_schema_preserves_each_time_meaning() -> None:
    response = FeishuPersonalSyncResponse(
        scope_id=UUID("00000000-0000-0000-0000-000000000202"),
        ingested_count=2,
        claimed_at=datetime(2026, 8, 8, 8, 0, tzinfo=UTC),
        window_start=datetime(2026, 8, 8, 7, 55, tzinfo=UTC),
        window_end=datetime(2026, 8, 8, 8, 0, tzinfo=UTC),
        completed_at=datetime(2026, 8, 8, 8, 3, tzinfo=UTC),
    )

    payload = response.model_dump(by_alias=True, mode="json")

    assert payload == {
        "scopeId": "00000000-0000-0000-0000-000000000202",
        "ingestedCount": 2,
        "claimedAt": "2026-08-08T08:00:00Z",
        "windowStart": "2026-08-08T07:55:00Z",
        "windowEnd": "2026-08-08T08:00:00Z",
        "completedAt": "2026-08-08T08:03:00Z",
    }
