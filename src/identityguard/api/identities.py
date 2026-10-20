"""Tenant-scoped identity reads."""

from __future__ import annotations

from fastapi import APIRouter, Header, Request

from identityguard.api.agents import _service_call, principal_or_401

router = APIRouter()


@router.get("/v1/identities/{identity_id}")
def get_identity(identity_id: str, request: Request, authorization: str | None = Header(default=None)) -> dict:
    who = principal_or_401(authorization)
    return _service_call(request, lambda: request.app.state.service.identity(who, identity_id))
