"""Investigation graph.

Order: retrieve, analyze, authorize, optional approval interrupt, execute,
verify, close. Authorize and the post-resume reauthorize call the same policy
code. A checkpoint cannot skip them.
"""

from __future__ import annotations

from datetime import timedelta
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from identityguard.harness.context import compact_evidence
from identityguard.harness.memory import remember
from identityguard.identity.authorization import action_fingerprint, authorize, reauthorize
from identityguard.identity.verification import verify_account
from identityguard.models.base import ModelTimeout, ModelUnavailable

MESSAGES = {
    "DENIED": "Policy denied the action. No write occurred.",
    "REJECTED": "Approval rejected. No write occurred.",
    "EXPIRED": "Approval expired. No write occurred.",
    "EVIDENCE_REJECTED": "Finding rejected. Cited evidence is not in the tenant record.",
    "FAILED": "Workflow failed. No write occurred.",
    "NO_ACTION": "No authorized action was proposed.",
    "AWAITING_APPROVAL": "Approval required before any write.",
    "VERIFIED": "Account state matches the approved action.",
    "UNVERIFIED": "Tool result was not confirmed by a reread. The workflow stopped.",
}


class InvestigationState(TypedDict, total=False):
    run_id: str
    tenant_id: str
    actor: str
    role: str
    goal: str
    subject_id: str
    evidence: list
    analysis: dict | None
    proposed_action: dict | None
    policy_decision: str
    policy_reasons: list
    approval_id: str
    status: str
    verification: str | None
    completed: bool
    message: str
    tool_result: dict | None
    model_error: str | None


def build_graph(store, tools, model, clock, checkpointer, *, ttl_seconds: int = 3600, max_attempts: int = 3):
    def retrieve(state: InvestigationState) -> dict:
        rows = store.search_evidence(state["tenant_id"], state["subject_id"])
        return {"evidence": compact_evidence(rows)}

    def analyze(state: InvestigationState) -> dict:
        last_error: Exception | None = None
        result = None
        for _ in range(max_attempts):
            try:
                result = model.analyze(
                    goal=state.get("goal") or "",
                    evidence=list(state.get("evidence") or []),
                    subject_id=state["subject_id"],
                )
                break
            except (ModelTimeout, ModelUnavailable) as exc:
                last_error = exc
        if result is None:
            return {
                "status": "FAILED",
                "model_error": type(last_error).__name__ if last_error else "model_error",
                "proposed_action": None,
                "analysis": None,
            }
        known = {row["evidence_id"] for row in state.get("evidence") or []}
        cited = [str(item) for item in result.get("evidence_ids") or []]
        action = result.get("recommended_action")
        if action and (not cited or not set(cited) <= known):
            return {"status": "EVIDENCE_REJECTED", "analysis": result, "proposed_action": None}
        return {"analysis": result, "proposed_action": action, "status": "RUNNING"}

    def authorize_node(state: InvestigationState) -> dict:
        subject_tenant = store.locate_tenant(state["subject_id"])
        # skip_approval on the model output is intentionally unread.
        decision = authorize(
            role=state.get("role") or "",
            caller_tenant=state["tenant_id"],
            subject_tenant=subject_tenant,
            action=state.get("proposed_action"),
        )
        name = decision["decision"]
        if name == "deny":
            return {"status": "DENIED", "policy_decision": "deny", "policy_reasons": decision["reasons"]}
        if name == "no_action":
            return {"status": "NO_ACTION", "policy_decision": "no_action", "policy_reasons": decision["reasons"]}
        if name == "needs_approval":
            return {
                "status": "AWAITING_APPROVAL",
                "policy_decision": "needs_approval",
                "policy_reasons": decision["reasons"],
            }
        return {"status": "RUNNING", "policy_decision": "allow", "policy_reasons": decision["reasons"]}

    def approval_node(state: InvestigationState) -> dict:
        approval_id = f"APR-{state['run_id'].removeprefix('SYN-RUN-')}"
        fingerprint = action_fingerprint(state.get("proposed_action"))
        expires_at = (clock.now() + timedelta(seconds=ttl_seconds)).strftime("%Y-%m-%dT%H:%M:%SZ")
        store.ensure_approval(
            approval_id=approval_id,
            run_id=state["run_id"],
            tenant_id=state["tenant_id"],
            requester=state["actor"],
            args_fingerprint=fingerprint,
            action=state.get("proposed_action"),
            expires_at=expires_at,
        )
        _persist(store, state, status="AWAITING_APPROVAL", approval_id=approval_id, completed=False)
        interrupt({"approval_id": approval_id, "status": "AWAITING_APPROVAL"})
        record = store.get_approval(state["tenant_id"], approval_id)
        outcome = reauthorize(record, clock.now(), fingerprint)
        if outcome != "ALLOW":
            return {
                "approval_id": approval_id,
                "status": outcome,
                "policy_decision": "deny",
            }
        return {"approval_id": approval_id, "status": "APPROVED", "policy_decision": "allow"}

    def execute(state: InvestigationState) -> dict:
        fingerprint = action_fingerprint(state.get("proposed_action"))
        record = store.get_approval(state["tenant_id"], state.get("approval_id", ""))
        outcome = reauthorize(record, clock.now(), fingerprint)
        if outcome != "ALLOW":
            return {"status": outcome, "policy_decision": "deny", "tool_result": None}
        result = tools.suspend_account(
            tenant_id=state["tenant_id"],
            identity_id=state["subject_id"],
            idempotency_key=state["run_id"],
        )
        return {"tool_result": result}

    def verify(state: InvestigationState) -> dict:
        if not state.get("tool_result"):
            return {}
        identity = store.get_identity(state["tenant_id"], state["subject_id"])
        return verify_account(identity, "suspended", state.get("tool_result"))

    def close(state: InvestigationState) -> dict:
        status = state.get("status") or "FAILED"
        completed = status == "VERIFIED"
        verification = state.get("verification")
        message = MESSAGES.get(status, "Workflow stopped. No write occurred.")
        _persist(
            store,
            state,
            status=status,
            approval_id=state.get("approval_id"),
            verification=verification,
            completed=completed,
            message=message,
        )
        remember(
            store,
            state["tenant_id"],
            state["run_id"],
            {
                "run_id": state["run_id"],
                "status": status,
                "subject_id": state["subject_id"],
                "completed": completed,
            },
        )
        store.audit(
            tenant_id=state["tenant_id"],
            run_id=state["run_id"],
            action="run",
            result=status,
            actor=state.get("actor"),
        )
        return {"status": status, "completed": completed, "message": message, "verification": verification}

    def after_analyze(state: InvestigationState) -> str:
        if state.get("status") in {"FAILED", "EVIDENCE_REJECTED"}:
            return "close"
        return "authorize"

    def after_authorize(state: InvestigationState) -> str:
        if state.get("policy_decision") == "needs_approval":
            return "approval"
        return "close"

    def after_approval(state: InvestigationState) -> str:
        if state.get("policy_decision") == "allow":
            return "execute"
        return "close"

    graph = StateGraph(InvestigationState)
    graph.add_node("retrieve", retrieve)
    graph.add_node("analyze", analyze)
    graph.add_node("authorize", authorize_node)
    graph.add_node("approval", approval_node)
    graph.add_node("execute", execute)
    graph.add_node("verify", verify)
    graph.add_node("close", close)
    graph.add_edge(START, "retrieve")
    graph.add_edge("retrieve", "analyze")
    graph.add_conditional_edges("analyze", after_analyze, {"authorize": "authorize", "close": "close"})
    graph.add_conditional_edges("authorize", after_authorize, {"approval": "approval", "close": "close"})
    graph.add_conditional_edges("approval", after_approval, {"execute": "execute", "close": "close"})
    graph.add_edge("execute", "verify")
    graph.add_edge("verify", "close")
    graph.add_edge("close", END)
    return graph.compile(checkpointer=checkpointer)


def _persist(store, state: InvestigationState, **fields) -> None:
    evidence = [
        {"evidence_id": row["evidence_id"], "kind": row["kind"], "summary": row["summary"]}
        for row in state.get("evidence") or []
    ]
    store.update_run(
        state["run_id"],
        state["tenant_id"],
        status=fields["status"],
        approval_id=fields.get("approval_id"),
        verification=fields.get("verification"),
        completed=fields.get("completed", False),
        message=fields.get("message", MESSAGES.get(fields["status"], "")),
        proposed_action=state.get("proposed_action"),
        evidence=evidence,
    )
