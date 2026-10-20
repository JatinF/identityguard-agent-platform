"""Policy gate for identity tools.

The operation is taken from the structured field. Free text cannot select a
tool, change the tenant, or satisfy an approval. High-risk tools stay closed
until an approval names a different person in the same tenant.
"""

from __future__ import annotations

from identityguard.directory import ASSIGNABLE_ROLES, Directory

OPERATIONS = {
    "lookup-account": {"risk": "low", "roles": frozenset({"reader", "operator", "approver"})},
    "disable-account": {"risk": "high", "roles": frozenset({"operator", "approver"})},
    "grant-role": {"risk": "high", "roles": frozenset({"operator", "approver"})},
    "export-audit": {"risk": "high", "roles": frozenset({"operator", "approver"})},
}

EXPORT_TARGET = "SYN-AUDIT"
FORBIDDEN_KEYS = frozenset({"password", "secret", "api_key", "ssn", "private_key"})


def forbidden_keys(payload: dict) -> list[str]:
    return sorted(key for key in payload if str(key).lower() in FORBIDDEN_KEYS)


def _approval_problems(state: dict, approval: dict) -> list[str]:
    problems: list[str] = []
    if approval.get("tenant") != state.get("tenant"):
        problems.append("approval tenant mismatch")
    if approval.get("request_id") != state.get("request_id"):
        problems.append("approval request mismatch")
    if approval.get("approver_role") != "approver":
        problems.append("approver role required")
    if not approval.get("approver") or approval.get("approver") == state.get("actor"):
        problems.append("self-approval denied")
    approval_id = str(approval.get("approval_id", ""))
    if not approval_id.startswith("APR-"):
        problems.append("approval id must start with APR-")
    return problems


def evaluate(state: dict, directory: Directory) -> dict:
    """Return allow, deny, or needs-approval. Tool is set only on allow."""
    reasons: list[str] = []
    operation = str(state.get("operation") or "")
    target = str(state.get("target") or "")
    tenant = str(state.get("tenant") or "")
    role = str(state.get("role") or "")
    request_id = str(state.get("request_id") or "")

    if not request_id.startswith("SYN-REQ-"):
        reasons.append("request id must start with SYN-REQ-")
    if tenant not in directory.tenants():
        reasons.append("unknown tenant")
    if role not in {"reader", "operator", "approver"}:
        reasons.append("unknown role")

    spec = OPERATIONS.get(operation)
    if spec is None:
        reasons.append("unknown operation")
    else:
        if role and role not in spec["roles"]:
            reasons.append("role cannot request this operation")
        if operation == "export-audit":
            if target != EXPORT_TARGET:
                reasons.append("export target must be SYN-AUDIT")
        else:
            if not target.startswith("SYN-USER-"):
                reasons.append("target must start with SYN-USER-")
            elif tenant in directory.tenants() and directory.get(tenant, target) is None:
                reasons.append("unknown target")
        if operation == "grant-role" and state.get("role_name") not in ASSIGNABLE_ROLES:
            reasons.append("role name is not assignable")

    if reasons:
        return {"decision": "deny", "reasons": reasons, "tool": None}

    assert spec is not None
    if spec["risk"] == "low":
        return {"decision": "allow", "reasons": [], "tool": operation}

    approval = state.get("approval")
    if not isinstance(approval, dict) or not approval:
        return {"decision": "needs-approval", "reasons": ["human approval required"], "tool": None}
    problems = _approval_problems(state, approval)
    if problems:
        return {"decision": "deny", "reasons": problems, "tool": None}
    return {"decision": "allow", "reasons": [], "tool": operation}
