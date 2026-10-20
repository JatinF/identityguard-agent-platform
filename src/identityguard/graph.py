"""LangGraph harness for one identity operation.

The graph pauses before a high-risk tool. Resuming loads the checkpoint and
evaluates the policy again, so a saved thread cannot skip the gate. Tool
failure stops in Close and leaves the directory unchanged.
"""

from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from identityguard.audit import AuditLog
from identityguard.directory import Directory
from identityguard.memory import TenantMemory
from identityguard.policy import evaluate


class RunState(TypedDict, total=False):
    request_id: str
    tenant: str
    actor: str
    role: str
    operation: str
    target: str
    role_name: str
    approval: dict | None
    decision: str
    deny_reasons: list[str]
    tool_name: str | None
    tool_result: dict | None
    status: str
    verified: bool
    contained: bool
    verify_detail: str
    fingerprint_before: str
    fingerprint_after: str


def build_graph(directory: Directory, memory: TenantMemory, audit: AuditLog, checkpointer, *, force_tool_down: bool = False):
    def intake(state: RunState) -> dict:
        tenant = str(state.get("tenant") or "")
        return {
            "approval": None,
            "tool_result": None,
            "verified": False,
            "contained": True,
            "role_name": state.get("role_name") or "",
            "fingerprint_before": directory.fingerprint(tenant),
        }

    def policy_node(state: RunState) -> dict:
        outcome = evaluate(state, directory)
        status = {"deny": "denied", "needs-approval": "awaiting-approval", "allow": "running"}[outcome["decision"]]
        return {
            "decision": outcome["decision"],
            "deny_reasons": outcome["reasons"],
            "tool_name": outcome["tool"],
            "status": status,
        }

    def route(state: RunState) -> str:
        if state.get("decision") == "allow":
            return "execute"
        if state.get("decision") == "needs-approval":
            return "approval"
        return "close"

    def approval_node(state: RunState) -> dict:
        payload = interrupt(
            {
                "request_id": state.get("request_id"),
                "tenant": state.get("tenant"),
                "operation": state.get("operation"),
                "target": state.get("target"),
            }
        )
        if not isinstance(payload, dict):
            payload = {}
        return {"approval": payload}

    def recheck(state: RunState) -> dict:
        outcome = evaluate(state, directory)
        if outcome["decision"] != "allow":
            reasons = list(outcome["reasons"])
            if outcome["decision"] == "needs-approval":
                reasons.append("approval did not clear the gate")
            return {
                "decision": "deny",
                "deny_reasons": reasons,
                "tool_name": None,
                "status": "denied",
            }
        return {
            "decision": "allow",
            "deny_reasons": [],
            "tool_name": outcome["tool"],
            "status": "running",
        }

    def execute_node(state: RunState) -> dict:
        if force_tool_down:
            return {
                "status": "failed",
                "tool_result": None,
                "tool_name": None,
                "verified": False,
                "verify_detail": "tool backend unavailable",
            }
        # The checkpoint can be resumed later. Re-evaluate so a saved thread cannot skip the gate.
        outcome = evaluate(state, directory)
        if outcome["decision"] != "allow" or not outcome["tool"]:
            return {
                "decision": "deny",
                "deny_reasons": list(outcome["reasons"]) + ["tool execution refused"],
                "status": "denied",
                "tool_result": None,
                "tool_name": None,
            }
        result = directory.apply(
            tenant=str(state["tenant"]),
            operation=str(outcome["tool"]),
            target=str(state["target"]),
            role_name=state.get("role_name"),
            idempotency_key=str(state["request_id"]),
            audit_rows=audit.for_tenant(str(state["tenant"])),
        )
        return {"tool_result": result, "tool_name": outcome["tool"], "status": "running"}

    def verify_node(state: RunState) -> dict:
        tenant = str(state.get("tenant") or "")
        after = directory.fingerprint(tenant)
        before = state.get("fingerprint_before")
        contained = after == before
        if state.get("status") == "failed" or not state.get("tool_result"):
            status = "failed" if state.get("status") == "failed" else "denied"
            verified = contained if status == "denied" else False
            return {
                "verified": verified,
                "contained": contained,
                "status": status,
                "fingerprint_after": after,
                "verify_detail": state.get("verify_detail") or "not executed",
            }
        ok, detail = _postcondition(state, directory, contained)
        return {
            "verified": ok,
            "contained": contained,
            "status": "verified" if ok else "failed",
            "verify_detail": detail,
            "fingerprint_after": after,
        }

    def close_node(state: RunState) -> dict:
        tenant = str(state.get("tenant") or "")
        after = directory.fingerprint(tenant)
        before = state.get("fingerprint_before")
        contained = after == before
        status = state.get("status") or "denied"
        if status == "awaiting-approval":
            status = "denied"
        if status == "denied":
            verified = contained
        elif status == "verified":
            verified = bool(state.get("verified"))
        else:
            verified = False
            status = "failed" if status == "failed" else status
        record = {
            "request_id": state.get("request_id"),
            "tenant": tenant,
            "actor": state.get("actor"),
            "operation": state.get("operation"),
            "target": state.get("target"),
            "decision": state.get("decision"),
            "status": status,
            "verified": verified,
        }
        if tenant:
            memory.write(tenant, f"run:{state.get('request_id')}", record)
        audit.write(action="run", result=status, **record)
        return {
            "status": status,
            "verified": verified,
            "contained": contained,
            "fingerprint_after": after,
        }

    graph = StateGraph(RunState)
    graph.add_node("intake", intake)
    graph.add_node("policy", policy_node)
    graph.add_node("approval", approval_node)
    graph.add_node("recheck", recheck)
    graph.add_node("execute", execute_node)
    graph.add_node("verify", verify_node)
    graph.add_node("close", close_node)
    graph.add_edge(START, "intake")
    graph.add_edge("intake", "policy")
    graph.add_conditional_edges("policy", route, {"execute": "execute", "approval": "approval", "close": "close"})
    graph.add_edge("approval", "recheck")
    graph.add_conditional_edges("recheck", route, {"execute": "execute", "approval": "close", "close": "close"})
    graph.add_edge("execute", "verify")
    graph.add_edge("verify", "close")
    graph.add_edge("close", END)
    return graph.compile(checkpointer=checkpointer)


def _postcondition(state: RunState, directory: Directory, contained: bool) -> tuple[bool, str]:
    operation = state.get("tool_name") or state.get("operation")
    tenant = str(state.get("tenant") or "")
    target = str(state.get("target") or "")
    result = state.get("tool_result") or {}
    if result.get("tenant") != tenant:
        return False, "tool result tenant mismatch"
    if operation == "lookup-account":
        account = directory.get(tenant, target)
        ok = bool(result.get("found")) and account is not None and result.get("status") == account["status"] and contained
        return ok, "lookup"
    if operation == "disable-account":
        account = directory.get(tenant, target)
        ok = account is not None and account["status"] == "disabled" and result.get("status") == "disabled"
        return ok, "disable"
    if operation == "grant-role":
        account = directory.get(tenant, target)
        role_name = state.get("role_name")
        ok = account is not None and role_name in account["roles"] and role_name in result.get("roles", [])
        return ok, "grant"
    if operation == "export-audit":
        records = result.get("records", [])
        ok = contained and all(row.get("tenant") == tenant for row in records)
        return ok, "export"
    return False, "no postcondition"
