"""One key, one run, one account transition."""

from tests.conftest import ALEX_GOAL, bearer


def test_repeated_start_returns_the_same_run(stack):
    client, service = stack
    headers = {**bearer("dev-operator-a"), "Idempotency-Key": "same-key"}
    payload = {"subject_id": "SYN-USER-ALEX", "goal": ALEX_GOAL, "tenant_id": "tenant-b"}
    first = client.post("/v1/agents/runs", headers=headers, json=payload).json()
    second = client.post("/v1/agents/runs", headers=headers, json=payload).json()
    assert first["run_id"] == second["run_id"]
    assert first["approval_id"] == second["approval_id"]
    assert first["tenant_id"] == "tenant-a"
    count = service.store.connection.execute("SELECT COUNT(*) AS n FROM runs").fetchone()["n"]
    assert count == 1


def test_repeated_decision_writes_once(stack):
    client, service = stack
    started = client.post(
        "/v1/agents/runs",
        headers={**bearer("dev-operator-a"), "Idempotency-Key": "write-once"},
        json={"subject_id": "SYN-USER-ALEX", "goal": ALEX_GOAL},
    ).json()
    path = f"/v1/approvals/{started['approval_id']}/decision"
    first = client.post(path, headers=bearer("dev-approver-a"), json={"decision": "approved"})
    second = client.post(path, headers=bearer("dev-approver-a"), json={"decision": "approved"})
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["status"] == "VERIFIED"
    assert second.json()["status"] == "VERIFIED"
    assert service.store.count_effects("SYN-USER-ALEX") == 1
    assert service.store.get_identity("tenant-a", "SYN-USER-ALEX")["status"] == "suspended"


def test_same_key_in_another_tenant_is_a_different_run(stack):
    client, _service = stack
    left = client.post(
        "/v1/agents/runs",
        headers={**bearer("dev-operator-a"), "Idempotency-Key": "shared-key"},
        json={"subject_id": "SYN-USER-ALEX", "goal": ALEX_GOAL},
    ).json()
    right = client.post(
        "/v1/agents/runs",
        headers={**bearer("dev-operator-b"), "Idempotency-Key": "shared-key"},
        json={"subject_id": "SYN-USER-BLAKE", "goal": "Investigate Blake Chen and suspend the account."},
    ).json()
    assert left["run_id"] != right["run_id"]
    assert left["tenant_id"] == "tenant-a"
    assert right["tenant_id"] == "tenant-b"
    hidden = client.get(f"/v1/agents/runs/{left['run_id']}", headers=bearer("dev-operator-b"))
    assert hidden.status_code == 404


def test_credential_fields_are_rejected(stack):
    client, service = stack
    response = client.post(
        "/v1/agents/runs",
        headers={**bearer("dev-operator-a"), "Idempotency-Key": "secret-1"},
        json={"subject_id": "SYN-USER-ALEX", "goal": ALEX_GOAL, "password": "hunter2-not-stored"},
    )
    assert response.status_code == 400
    text = service.store.audit_text("tenant-a")
    assert "hunter2-not-stored" not in text
    assert "password" not in text
    assert service.store.find_idempotency("tenant-a", "secret-1") is None
