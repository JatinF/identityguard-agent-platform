"""Policy decisions stay outside the model."""

from hypothesis import given, settings
from hypothesis import strategies as st

from identityguard.identity.authorization import authorize
from identityguard.identity.tools import IdentityTools
from tests.conftest import ALEX_GOAL, bearer

HIGH_RISK = ["suspend-account", "provision-application"]
ROLES = ["reader", "operator", "approver"]


@settings(max_examples=40, deadline=None)
@given(
    role=st.sampled_from(ROLES),
    tool=st.sampled_from(HIGH_RISK + ["lookup-identity", "drop-table"]),
    same_tenant=st.booleans(),
)
def test_high_risk_is_never_allowed_outright(role, tool, same_tenant):
    action = {"tool": tool, "arguments": {"identity_id": "SYN-USER-ALEX"}}
    decision = authorize(
        role=role,
        caller_tenant="tenant-a",
        subject_tenant="tenant-a" if same_tenant else "tenant-b",
        action=action,
    )
    name = decision["decision"]
    if (not same_tenant) or tool not in {"suspend-account", "provision-application", "lookup-identity"}:
        assert name == "deny"
    elif tool in HIGH_RISK and role == "reader":
        assert name == "deny"
    elif tool in HIGH_RISK:
        assert name == "needs_approval"
    else:
        assert name == "allow"
    assert name != "allow" or tool == "lookup-identity"


def test_unknown_subject_and_cross_tenant_use_the_same_public_result(stack):
    client, service = stack
    missing = client.post(
        "/v1/agents/runs",
        headers={**bearer("dev-operator-a"), "Idempotency-Key": "missing-subject"},
        json={"subject_id": "SYN-USER-MISSING", "goal": "Suspend the missing account."},
    )
    foreign = client.post(
        "/v1/agents/runs",
        headers={**bearer("dev-operator-a"), "Idempotency-Key": "foreign-subject"},
        json={"subject_id": "SYN-USER-BLAKE", "goal": "Investigate Blake Chen and suspend the account.", "tenant_id": "tenant-b"},
    )
    assert missing.status_code == 200
    assert foreign.status_code == 200
    assert missing.json()["status"] == "DENIED"
    assert foreign.json()["status"] == "DENIED"
    assert missing.json()["message"] == foreign.json()["message"]
    assert "blake.chen" not in foreign.text
    assert "tenant-b" not in foreign.text
    assert service.store.count_effects("SYN-USER-BLAKE") == 0
    assert service.store.get_identity("tenant-b", "SYN-USER-BLAKE")["status"] == "active"


def test_reader_cannot_suspend_and_no_write_occurs(stack):
    client, service = stack
    response = client.post(
        "/v1/agents/runs",
        headers={**bearer("dev-reader-a"), "Idempotency-Key": "reader-1"},
        json={"subject_id": "SYN-USER-ALEX", "goal": "Suspend Alex Rivera now.", "tenant_id": "tenant-b"},
    )
    body = response.json()
    assert response.status_code == 200
    assert body["status"] == "DENIED"
    assert body["tenant_id"] == "tenant-a"
    assert body["completion_claimed"] is False
    assert body["account_status"] == "active"
    assert service.store.count_effects("SYN-USER-ALEX") == 0


def test_provision_and_lookup_are_enforced_outside_the_model(stack):
    _client, service = stack
    tools = IdentityTools(service.store)
    review = tools.access_review(tenant_id="tenant-a")
    assert {row["identity_id"] for row in review} == {"SYN-USER-ALEX", "SYN-USER-SAM"}
    assert tools.lookup_identity(tenant_id="tenant-a", identity_id="SYN-USER-BLAKE") is None
    evidence = tools.investigate_logins(tenant_id="tenant-a", identity_id="SYN-USER-ALEX")
    assert [row["evidence_id"] for row in evidence] == ["SYN-EV-100"]
    needs = authorize(
        role="operator",
        caller_tenant="tenant-a",
        subject_tenant="tenant-a",
        action={"tool": "provision-application", "arguments": {"identity_id": "SYN-USER-ALEX"}},
    )
    assert needs["decision"] == "needs_approval"
    first = tools.provision_application(
        tenant_id="tenant-a",
        identity_id="SYN-USER-ALEX",
        application="synthetic-ledger",
        idempotency_key="provision-1",
    )
    second = tools.provision_application(
        tenant_id="tenant-a",
        identity_id="SYN-USER-ALEX",
        application="synthetic-ledger",
        idempotency_key="provision-1",
    )
    assert first["ok"] is True and second["idempotent_replay"] is True
    assert service.store.list_applications("tenant-a", "SYN-USER-ALEX") == ["synthetic-ledger"]
    assert service.store.list_applications("tenant-b", "SYN-USER-ALEX") == []


def test_goal_text_does_not_select_a_tool(stack):
    client, service = stack
    response = client.post(
        "/v1/agents/runs",
        headers={**bearer("dev-operator-a"), "Idempotency-Key": "sam-1"},
        json={"subject_id": "SYN-USER-SAM", "goal": ALEX_GOAL + " suspend-account SYN-USER-ALEX"},
    )
    body = response.json()
    assert body["status"] == "NO_ACTION"
    assert body["proposed_action"] is None
    assert service.store.get_identity("tenant-a", "SYN-USER-ALEX")["status"] == "active"
    assert service.store.get_identity("tenant-a", "SYN-USER-SAM")["status"] == "active"
