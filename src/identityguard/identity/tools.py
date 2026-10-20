"""Identity tools.

suspend_account is idempotent on the request key. skip_write lets a test
force the tool to claim success while leaving the account unchanged.
"""

from __future__ import annotations


class IdentityTools:
    def __init__(self, store, *, skip_write: bool = False):
        self.store = store
        self.skip_write = skip_write

    def suspend_account(self, *, tenant_id: str, identity_id: str, idempotency_key: str) -> dict:
        prior = self.store.get_effect(idempotency_key)
        if prior is not None:
            return {"ok": True, "status": prior["resulting_status"], "idempotent_replay": True}
        if self.skip_write:
            return {"ok": True, "status": "suspended", "idempotent_replay": False}
        updated = self.store.set_status(tenant_id, identity_id, "suspended")
        if not updated:
            return {"ok": False, "status": None, "idempotent_replay": False}
        self.store.save_effect(idempotency_key, tenant_id, identity_id, "suspended")
        return {"ok": True, "status": "suspended", "idempotent_replay": False}

    def write_count(self, identity_id: str) -> int:
        return self.store.count_effects(identity_id)

    def lookup_identity(self, *, tenant_id: str, identity_id: str) -> dict | None:
        return self.store.get_identity(tenant_id, identity_id)

    def access_review(self, *, tenant_id: str) -> list[dict]:
        return self.store.list_identities(tenant_id)

    def investigate_logins(self, *, tenant_id: str, identity_id: str) -> list[dict]:
        return self.store.search_evidence(tenant_id, identity_id)

    def provision_application(self, *, tenant_id: str, identity_id: str, application: str, idempotency_key: str) -> dict:
        prior = self.store.get_effect(idempotency_key)
        if prior is not None:
            return {"ok": True, "status": prior["resulting_status"], "idempotent_replay": True}
        if self.store.get_identity(tenant_id, identity_id) is None:
            return {"ok": False, "status": None, "idempotent_replay": False}
        self.store.save_application(tenant_id, identity_id, application)
        self.store.save_effect(idempotency_key, tenant_id, identity_id, "provisioned")
        return {"ok": True, "status": "provisioned", "idempotent_replay": False}
