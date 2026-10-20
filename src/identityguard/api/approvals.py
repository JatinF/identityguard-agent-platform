"""Human approval decisions."""

from __future__ import annotations

from fastapi import APIRouter, Header, Request

from identityguard.api.agents import _body, _service_call, principal_or_401

router = APIRouter()


@router.post("/v1/approvals/{approval_id}/decision")
async def decide(approval_id: str, request: Request, authorization: str | None = Header(default=None)) -> dict:
    who = principal_or_401(authorization)
    payload = await _body(request, who)
    decision = str(payload.get("decision") or "")
    view = _service_call(request, lambda: request.app.state.service.decide(who, approval_id, decision))
    request.app.state.approvals.labels(decision=decision or "invalid").inc()
    request.app.state.runs.labels(status=view["status"]).inc()
    return view
