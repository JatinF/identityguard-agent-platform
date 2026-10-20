"""Investigation run routes."""

from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Request

from identityguard.harness.recovery import ServiceError, forbidden_keys
from identityguard.principals import AuthError, authenticate

router = APIRouter()


def principal_or_401(authorization: str | None):
    try:
        return authenticate(authorization)
    except AuthError as exc:
        raise HTTPException(status_code=401, detail="unauthorized") from exc


def _service_call(request: Request, func):
    try:
        return func()
    except ServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


async def _body(request: Request, who=None) -> dict:
    payload = await request.json()
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="body must be an object")
    banned = forbidden_keys(payload)
    if banned:
        if who is not None:
            request.app.state.service.store.audit(
                tenant_id=who.tenant_id,
                run_id=None,
                action="request",
                result="deny",
                actor=who.token_name,
            )
        raise HTTPException(status_code=400, detail="credential material is not accepted")
    return payload


@router.post("/v1/agents/runs")
async def start_run(
    request: Request,
    authorization: str | None = Header(default=None),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict:
    who = principal_or_401(authorization)
    payload = await _body(request, who)
    header_key = (idempotency_key or "").strip()
    body_key = str(payload.get("idempotency_key") or "").strip()
    if header_key and body_key and header_key != body_key:
        raise HTTPException(status_code=400, detail="idempotency key mismatch")
    key = header_key or body_key
    view = _service_call(
        request,
        lambda: request.app.state.service.start(
            who,
            subject_id=str(payload.get("subject_id") or ""),
            goal=str(payload.get("goal") or ""),
            idempotency_key=key,
            body_tenant=payload.get("tenant_id") if isinstance(payload.get("tenant_id"), str) else None,
        ),
    )
    request.app.state.runs.labels(status=view["status"]).inc()
    return view


@router.get("/v1/agents/runs/{run_id}")
def get_run(run_id: str, request: Request, authorization: str | None = Header(default=None)) -> dict:
    who = principal_or_401(authorization)
    return _service_call(request, lambda: request.app.state.service.view(who, run_id))


@router.post("/v1/agents/runs/{run_id}/resume")
async def resume_run(run_id: str, request: Request, authorization: str | None = Header(default=None)) -> dict:
    who = principal_or_401(authorization)
    payload = await _body(request, who)
    del payload
    view = _service_call(request, lambda: request.app.state.service.resume(who, run_id))
    request.app.state.runs.labels(status=view["status"]).inc()
    return view
