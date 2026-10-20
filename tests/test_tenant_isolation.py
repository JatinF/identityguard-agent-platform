"""Tenant A cannot read Tenant B."""

import os

import pytest

from tests.conftest import ALEX_GOAL, bearer


def test_identity_and_run_reads_stay_in_the_token_tenant(stack):
    client, service = stack
    own = client.get("/v1/identities/SYN-USER-ALEX", headers=bearer("dev-operator-a"))
    other = client.get("/v1/identities/SYN-USER-BLAKE", headers=bearer("dev-operator-a"))
    assert own.status_code == 200
    assert own.json()["email"] == "alex.rivera@example.invalid"
    assert other.status_code == 404
    started = client.post(
        "/v1/agents/runs",
        headers={**bearer("dev-operator-a"), "Idempotency-Key": "iso-1"},
        json={"subject_id": "SYN-USER-ALEX", "goal": ALEX_GOAL, "tenant_id": "tenant-b"},
    ).json()
    assert started["tenant_id"] == "tenant-a"
    denied = client.get(f"/v1/agents/runs/{started['run_id']}", headers=bearer("dev-operator-b"))
    assert denied.status_code == 404
    remembered = service.store.read_memory("tenant-b", f"run:{started['run_id']}")
    assert remembered is None
    leaked = service.store.search_evidence("tenant-a", "SYN-USER-BLAKE")
    assert leaked == []
    similar = service.store.search_similar("tenant-a", "OVERRIDE-TENANT-B")
    assert similar
    assert all(row["tenant_id"] == "tenant-a" for row in similar)
    assert all("OVERRIDE-TENANT-B" not in row["summary"] for row in similar)


def test_missing_token_is_unauthorized(stack):
    client, _service = stack
    assert client.get("/v1/identities/SYN-USER-ALEX").status_code == 401
    health = client.get("/healthz")
    assert health.status_code == 200
    assert health.json()["real_accounts"] == 0


@pytest.mark.skipif(not os.environ.get("DATABASE_URL"), reason="DATABASE_URL is not set")
def test_postgres_row_level_security_hides_other_tenants():
    from identityguard.storage.postgres import PostgresStore

    store = PostgresStore(os.environ["DATABASE_URL"])
    store.migrate()
    store.seed_if_empty()
    visible = set(store.visible_identity_ids("tenant-a"))
    assert "SYN-USER-ALEX" in visible
    assert "SYN-USER-SAM" in visible
    assert "SYN-USER-BLAKE" not in visible
    assert set(store.visible_identity_ids("tenant-b")) == {"SYN-USER-BLAKE"}
    assert store.visible_without_tenant() == []
