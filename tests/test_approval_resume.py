"""Approval, expiry, and crash resume."""

from datetime import datetime, timezone

from identityguard.harness.recovery import Clock, open_service
from identityguard.principals import authenticate
from tests.conftest import ALEX_GOAL, bearer


def _start(client, key="alex-approve"):
    response = client.post(
        "/v1/agents/runs",
        headers={**bearer("dev-operator-a"), "Idempotency-Key": key},
        json={"subject_id": "SYN-USER-ALEX", "goal": ALEX_GOAL},
    )
    assert response.status_code == 200
    return response.json()


def test_rejected_approval_does_not_write(stack):
    client, service = stack
    started = _start(client, "reject-1")
    assert started["status"] == "AWAITING_APPROVAL"
    decided = client.post(
        f"/v1/approvals/{started['approval_id']}/decision",
        headers=bearer("dev-approver-a"),
        json={"decision": "rejected"},
    )
    body = decided.json()
    assert decided.status_code == 200
    assert body["status"] == "REJECTED"
    assert body["completion_claimed"] is False
    assert "success" not in body["message"].lower()
    assert body["account_status"] == "active"
    assert service.store.count_effects("SYN-USER-ALEX") == 0


def test_expired_approval_does_not_write(tmp_path):
    service = open_service(tmp_path, clock=Clock(datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)), ttl_seconds=60)
    try:
        operator = authenticate("Bearer dev-operator-a")
        approver = authenticate("Bearer dev-approver-a")
        started = service.start(operator, subject_id="SYN-USER-ALEX", goal=ALEX_GOAL, idempotency_key="expire-1")
        service.clock.advance(120)
        decided = service.decide(approver, started["approval_id"], "approved")
        assert decided["status"] == "EXPIRED"
        assert decided["completion_claimed"] is False
        assert "success" not in decided["message"].lower()
        assert service.store.get_identity("tenant-a", "SYN-USER-ALEX")["status"] == "active"
        assert service.store.count_effects("SYN-USER-ALEX") == 0
    finally:
        service.close()


def test_pending_resume_does_not_execute_and_expired_resume_stops(tmp_path):
    service = open_service(tmp_path, clock=Clock(datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)), ttl_seconds=60)
    try:
        operator = authenticate("Bearer dev-operator-a")
        started = service.start(operator, subject_id="SYN-USER-ALEX", goal=ALEX_GOAL, idempotency_key="pause-1")
        waiting = service.resume(operator, started["run_id"])
        assert waiting["status"] == "AWAITING_APPROVAL"
        assert service.store.count_effects("SYN-USER-ALEX") == 0
        service.clock.advance(120)
        expired = service.resume(operator, started["run_id"])
        assert expired["status"] == "EXPIRED"
        assert service.store.count_effects("SYN-USER-ALEX") == 0
    finally:
        service.close()


def test_self_approval_is_rejected(stack):
    client, service = stack
    response = client.post(
        "/v1/agents/runs",
        headers={**bearer("dev-approver-a"), "Idempotency-Key": "self-1"},
        json={"subject_id": "SYN-USER-ALEX", "goal": ALEX_GOAL},
    )
    started = response.json()
    assert started["status"] == "AWAITING_APPROVAL"
    denied = client.post(
        f"/v1/approvals/{started['approval_id']}/decision",
        headers=bearer("dev-approver-a"),
        json={"decision": "approved"},
    )
    assert denied.status_code == 403
    assert service.store.get_identity("tenant-a", "SYN-USER-ALEX")["status"] == "active"
    assert service.store.count_effects("SYN-USER-ALEX") == 0


def test_crash_then_resume_writes_once(tmp_path):
    moment = datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)
    operator = authenticate("Bearer dev-operator-a")
    approver = authenticate("Bearer dev-approver-a")
    service = open_service(tmp_path, clock=Clock(moment))
    started = service.start(operator, subject_id="SYN-USER-ALEX", goal=ALEX_GOAL, idempotency_key="crash-1")
    assert started["status"] == "AWAITING_APPROVAL"
    service.close()

    reopened = open_service(tmp_path, clock=Clock(moment))
    try:
        decided = reopened.decide(approver, started["approval_id"], "approved")
        assert decided["status"] == "VERIFIED"
        assert decided["completion_claimed"] is True
        assert decided["account_status"] == "suspended"
        assert reopened.store.count_effects("SYN-USER-ALEX") == 1
        again = reopened.resume(operator, started["run_id"])
        repeated = reopened.decide(approver, started["approval_id"], "approved")
        assert again["status"] == "VERIFIED"
        assert repeated["status"] == "VERIFIED"
        assert reopened.store.count_effects("SYN-USER-ALEX") == 1
    finally:
        reopened.close()


def test_other_tenant_approver_cannot_see_the_request(stack):
    client, _service = stack
    started = _start(client, "cross-approve")
    response = client.post(
        f"/v1/approvals/{started['approval_id']}/decision",
        headers=bearer("dev-approver-b"),
        json={"decision": "approved"},
    )
    assert response.status_code == 404
