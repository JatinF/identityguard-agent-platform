"""Server-side authorization.

The model may recommend an action or set skip_approval. Neither value grants
permission. High-risk tools stay closed until a different approver accepts the
exact argument fingerprint.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime

HIGH_RISK_TOOLS = frozenset({"suspend-account", "provision-application"})
KNOWN_TOOLS = HIGH_RISK_TOOLS | frozenset({"lookup-identity"})
REQUEST_ROLES = {
    "lookup-identity": frozenset({"reader", "operator", "approver"}),
    "suspend-account": frozenset({"operator", "approver"}),
    "provision-application": frozenset({"operator", "approver"}),
}


def action_fingerprint(action: dict | None) -> str:
    payload = action or {}
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def authorize(*, role: str, caller_tenant: str, subject_tenant: str | None, action: dict | None) -> dict:
    # Tenant checks run before the action so a cross-tenant subject is denied
    # even when the model proposes nothing. Callers see one public denial.
    if subject_tenant is None:
        return {"decision": "deny", "reasons": ["unknown target"]}
    if subject_tenant != caller_tenant:
        return {"decision": "deny", "reasons": ["tenant boundary"]}
    if action is None:
        return {"decision": "no_action", "reasons": ["no action proposed"]}
    tool = str(action.get("tool") or "")
    if tool not in KNOWN_TOOLS:
        return {"decision": "deny", "reasons": ["unknown tool"]}
    if role not in REQUEST_ROLES[tool]:
        return {"decision": "deny", "reasons": ["role cannot request this action"]}
    if tool in HIGH_RISK_TOOLS:
        return {"decision": "needs_approval", "reasons": ["human approval required"]}
    return {"decision": "allow", "reasons": []}


def reauthorize(record: dict | None, now: datetime, expected_fingerprint: str) -> str:
    """Return ALLOW, or the terminal status that must stop the tool."""
    if record is None:
        return "DENIED"
    if record.get("args_fingerprint") != expected_fingerprint:
        return "DENIED"
    expires_at = datetime.fromisoformat(str(record["expires_at"]).replace("Z", "+00:00"))
    if expires_at <= now:
        return "EXPIRED"
    decision = record.get("decision")
    if decision in {None, "", "pending"}:
        return "AWAITING_APPROVAL"
    if decision == "rejected":
        return "REJECTED"
    if decision != "approved":
        return "DENIED"
    if record.get("approver_role") != "approver":
        return "DENIED"
    if not record.get("approver") or record.get("approver") == record.get("requester"):
        return "DENIED"
    if record.get("tenant_id") != record.get("approver_tenant"):
        return "DENIED"
    return "ALLOW"
