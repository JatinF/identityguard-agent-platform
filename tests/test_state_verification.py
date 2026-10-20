"""A tool success string is not completion."""

from identityguard.harness.context import compact_evidence
from identityguard.harness.recovery import open_service
from identityguard.models.mock_adapter import InventingModel
from identityguard.principals import authenticate
from tests.conftest import ALEX_GOAL, bearer


def test_verified_suspend_matches_the_reread(stack):
    client, service = stack
    started = client.post(
        "/v1/agents/runs",
        headers={**bearer("dev-operator-a"), "Idempotency-Key": "verify-1"},
        json={"subject_id": "SYN-USER-ALEX", "goal": ALEX_GOAL},
    ).json()
    decided = client.post(
        f"/v1/approvals/{started['approval_id']}/decision",
        headers=bearer("dev-approver-a"),
        json={"decision": "approved"},
    ).json()
    assert decided["status"] == "VERIFIED"
    assert decided["verification"] == "VERIFIED"
    assert decided["completion_claimed"] is True
    assert decided["account_status"] == "suspended"
    assert service.tools.write_count("SYN-USER-ALEX") == 1


def test_reported_success_without_a_state_change_is_unverified(tmp_path):
    service = open_service(tmp_path, skip_write=True)
    try:
        operator = authenticate("Bearer dev-operator-a")
        approver = authenticate("Bearer dev-approver-a")
        started = service.start(operator, subject_id="SYN-USER-ALEX", goal=ALEX_GOAL, idempotency_key="skip-1")
        decided = service.decide(approver, started["approval_id"], "approved")
        assert decided["status"] == "UNVERIFIED"
        assert decided["completion_claimed"] is False
        assert decided["completed"] is False
        assert "success" not in decided["message"].lower()
        assert "not confirmed" in decided["message"].lower()
        assert service.store.get_identity("tenant-a", "SYN-USER-ALEX")["status"] == "active"
        assert service.store.count_effects("SYN-USER-ALEX") == 0
    finally:
        service.close()


def test_invented_evidence_is_rejected(tmp_path):
    service = open_service(tmp_path, model=InventingModel())
    try:
        operator = authenticate("Bearer dev-operator-a")
        view = service.start(operator, subject_id="SYN-USER-ALEX", goal=ALEX_GOAL, idempotency_key="invent-1")
        assert view["status"] == "EVIDENCE_REJECTED"
        assert view["proposed_action"] is None
        assert view["completion_claimed"] is False
        assert "success" not in view["message"].lower()
        assert service.store.get_identity("tenant-a", "SYN-USER-ALEX")["status"] == "active"
        assert service.store.count_effects("SYN-USER-ALEX") == 0
    finally:
        service.close()


def test_context_compaction_keeps_the_evidence_id():
    rows = [
        {
            "evidence_id": "SYN-EV-100",
            "tenant_id": "tenant-a",
            "subject_id": "SYN-USER-ALEX",
            "kind": "suspicious-login",
            "summary": "short summary",
            "body": "x" * 800,
        }
    ]
    compacted = compact_evidence(rows, budget=500)
    assert compacted[0]["evidence_id"] == "SYN-EV-100"
    assert compacted[0]["body"] == "short summary"
    assert compacted[0]["kind"] == "suspicious-login"
