"""Synthetic account directory.

Accounts are fixtures. Identifiers start with SYN-USER-. The directory refuses
a seed file that declares real accounts. Tool effects are idempotent per
request id so a resumed run does not apply the same change twice.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ASSIGNABLE_ROLES = ("reader", "operator", "approver")
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SEED = REPO_ROOT / "data" / "synthetic_directory.json"


class DirectoryError(ValueError):
    pass


class Directory:
    def __init__(self, accounts: list[dict]):
        self._accounts: dict[str, dict[str, dict]] = {}
        self._done: dict[str, dict] = {}
        for row in accounts:
            tenant = str(row["tenant"])
            user_id = str(row["id"])
            if not user_id.startswith("SYN-USER-"):
                raise DirectoryError("seed account ids must start with SYN-USER-")
            self._accounts.setdefault(tenant, {})[user_id] = {
                "status": row.get("status", "active"),
                "roles": sorted(set(row.get("roles", []))),
            }

    @classmethod
    def from_seed(cls, path: Path | None = None) -> Directory:
        payload = json.loads((path or DEFAULT_SEED).read_text(encoding="utf-8"))
        if payload.get("real_accounts") != 0:
            raise DirectoryError("seed must declare real_accounts = 0")
        return cls(list(payload["accounts"]))

    def tenants(self) -> set[str]:
        return set(self._accounts)

    def get(self, tenant: str, user_id: str) -> dict | None:
        row = self._accounts.get(tenant, {}).get(user_id)
        if row is None:
            return None
        return {
            "id": user_id,
            "tenant": tenant,
            "status": row["status"],
            "roles": list(row["roles"]),
        }

    def fingerprint(self, tenant: str) -> str:
        rows = self._accounts.get(tenant, {})
        ordered = {
            user: {"roles": list(rows[user]["roles"]), "status": rows[user]["status"]}
            for user in sorted(rows)
        }
        blob = json.dumps(ordered, sort_keys=True)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def apply(
        self,
        *,
        tenant: str,
        operation: str,
        target: str,
        role_name: str | None,
        idempotency_key: str,
        audit_rows: list[dict],
    ) -> dict:
        if idempotency_key in self._done:
            return {**self._done[idempotency_key], "idempotent_replay": True}
        if operation == "lookup-account":
            account = self.get(tenant, target)
            result = {
                "operation": operation,
                "found": account is not None,
                "id": target,
                "tenant": tenant,
                "status": None if account is None else account["status"],
                "roles": [] if account is None else account["roles"],
            }
        elif operation == "disable-account":
            self._accounts[tenant][target]["status"] = "disabled"
            result = {"operation": operation, "id": target, "tenant": tenant, "status": "disabled"}
        elif operation == "grant-role":
            if role_name not in ASSIGNABLE_ROLES:
                raise DirectoryError("role name is not assignable")
            roles = self._accounts[tenant][target]["roles"]
            if role_name not in roles:
                roles.append(role_name)
                roles.sort()
            result = {
                "operation": operation,
                "id": target,
                "tenant": tenant,
                "roles": list(roles),
            }
        elif operation == "export-audit":
            records = [
                {
                    "action": row.get("action"),
                    "actor": row.get("actor"),
                    "request_id": row.get("request_id"),
                    "result": row.get("result"),
                    "tenant": row.get("tenant"),
                }
                for row in audit_rows
                if row.get("tenant") == tenant
            ]
            result = {"operation": operation, "tenant": tenant, "records": records}
        else:
            raise DirectoryError("unknown operation")
        self._done[idempotency_key] = result
        return {**result, "idempotent_replay": False}
