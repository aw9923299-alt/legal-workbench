from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from legal_workbench.domain.entities import AgentAttemptLease, AgentRunAttempt
from legal_workbench.domain.enums import AgentAttemptStatus
from legal_workbench.domain.errors import StaleAgentAttemptError

NOW = datetime(2026, 8, 3, 9, 0, tzinfo=UTC)


def _running_attempt() -> tuple[AgentRunAttempt, AgentAttemptLease]:
    run_id = uuid4()
    token = uuid4()
    attempt = AgentRunAttempt.start(
        run_id=run_id,
        attempt_number=2,
        lease_token=token,
        worker_id="worker-current",
        lease_expires_at=NOW + timedelta(seconds=60),
        now=NOW,
    )
    return attempt, AgentAttemptLease(
        run_id=run_id,
        attempt_number=2,
        lease_token=token,
    )


@pytest.mark.parametrize(
    "wrong_lease",
    [
        lambda lease: AgentAttemptLease(
            run_id=uuid4(),
            attempt_number=lease.attempt_number,
            lease_token=lease.lease_token,
        ),
        lambda lease: AgentAttemptLease(
            run_id=lease.run_id,
            attempt_number=lease.attempt_number + 1,
            lease_token=lease.lease_token,
        ),
        lambda lease: AgentAttemptLease(
            run_id=lease.run_id,
            attempt_number=lease.attempt_number,
            lease_token=uuid4(),
        ),
    ],
)
def test_completion_rejects_every_mismatched_fencing_value(wrong_lease) -> None:  # type: ignore[no-untyped-def]
    attempt, lease = _running_attempt()

    with pytest.raises(StaleAgentAttemptError):
        attempt.complete(wrong_lease(lease), now=NOW + timedelta(seconds=10))

    assert attempt.status == AgentAttemptStatus.RUNNING
    assert attempt.finished_at is None


def test_expired_attempt_rejects_late_worker_completion() -> None:
    attempt, lease = _running_attempt()
    attempt.expire(now=NOW + timedelta(seconds=61))

    with pytest.raises(StaleAgentAttemptError):
        attempt.complete(lease, now=NOW + timedelta(seconds=62))

    assert attempt.status == AgentAttemptStatus.EXPIRED
    assert attempt.finished_at == NOW + timedelta(seconds=61)


def test_matching_attempt_completes_exactly_once() -> None:
    attempt, lease = _running_attempt()

    attempt.complete(lease, now=NOW + timedelta(seconds=10))

    assert attempt.status == AgentAttemptStatus.COMPLETED
    assert attempt.finished_at == NOW + timedelta(seconds=10)
    with pytest.raises(StaleAgentAttemptError):
        attempt.complete(lease, now=NOW + timedelta(seconds=11))


def test_heartbeat_requires_current_lease_and_extends_expiry() -> None:
    attempt, lease = _running_attempt()
    heartbeat_at = NOW + timedelta(seconds=10)
    lease_expires_at = NOW + timedelta(seconds=70)

    attempt.heartbeat(
        lease,
        heartbeat_at=heartbeat_at,
        lease_expires_at=lease_expires_at,
    )

    assert attempt.heartbeat_at == heartbeat_at
    assert attempt.lease_expires_at == lease_expires_at
    with pytest.raises(StaleAgentAttemptError):
        attempt.heartbeat(
            AgentAttemptLease(
                run_id=lease.run_id,
                attempt_number=lease.attempt_number,
                lease_token=uuid4(),
            ),
            heartbeat_at=heartbeat_at,
            lease_expires_at=lease_expires_at,
        )


@pytest.mark.parametrize(
    "terminal_status",
    [
        AgentAttemptStatus.FAILED,
        AgentAttemptStatus.TIMED_OUT,
        AgentAttemptStatus.CANCELLED,
    ],
)
def test_failure_requires_current_lease_and_records_terminal_status(
    terminal_status: AgentAttemptStatus,
) -> None:
    attempt, lease = _running_attempt()

    attempt.fail(
        lease,
        status=terminal_status,
        failure_code="AGENT_RUNTIME_FAILURE",
        failure_message="safe summary",
        now=NOW + timedelta(seconds=10),
    )

    assert attempt.status == terminal_status
    assert attempt.failure_code == "AGENT_RUNTIME_FAILURE"
    assert attempt.failure_message == "safe summary"
    with pytest.raises(StaleAgentAttemptError):
        attempt.complete(lease, now=NOW + timedelta(seconds=11))
