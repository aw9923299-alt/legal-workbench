from __future__ import annotations

from typing import Any


def test_scheduler_heartbeat_is_independent_of_asyncio_event_loops(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from legal_workbench.infrastructure import redis_client
    from legal_workbench.workers.tasks import scheduler_heartbeat

    writes: list[tuple[str, str, int]] = []
    closes: list[bool] = []

    class FakeSyncRedis:
        def set(self, key: str, value: str, *, ex: int) -> None:
            writes.append((key, value, ex))

        def close(self) -> None:
            closes.append(True)

    def reject_async_client() -> Any:
        raise AssertionError("Celery sync heartbeat must not reuse an async Redis client")

    monkeypatch.setattr(redis_client, "get_redis_client", reject_async_client)
    monkeypatch.setattr("redis.Redis.from_url", lambda *args, **kwargs: FakeSyncRedis())

    first = scheduler_heartbeat()
    second = scheduler_heartbeat()

    assert first["heartbeatAt"] <= second["heartbeatAt"]
    assert [value[0] for value in writes] == [
        "legal-workbench:scheduler-heartbeat",
        "legal-workbench:scheduler-heartbeat",
    ]
    assert [value[2] for value in writes] == [90, 90]
    assert closes == [True, True]
