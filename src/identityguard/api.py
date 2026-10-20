"""HTTP entry for the harness.

Dev tokens are fixtures. A deployment replaces them with the site identity
provider. Metrics are process counters.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import PlainTextResponse

from identityguard.auth import DEV_TOKENS, AuthError, authenticate
from identityguard.harness import HarnessError, open_harness


def create_app(audit_path: Path, db_path: Path, tokens: dict | None = None, *, force_tool_down: bool = False) -> FastAPI:
    app = FastAPI(title="IdentityGuard agent harness", version="0.1.0")
    harness = open_harness(db_path, audit_path, force_tool_down=force_tool_down)
    app.state.harness = harness
    token_map = tokens if tokens is not None else dict(DEV_TOKENS)
    metrics = {"runs": 0, "denied": 0}

    def principal(authorization: str | None):
        try:
            return authenticate(authorization, token_map)
        except AuthError as exc:
            harness.audit.write(action="auth", result="deny", detail=str(exc))
            raise HTTPException(status_code=401, detail="unauthorized") from exc

    @app.get("/healthz")
    def healthz() -> dict:
        return {"status": "ok", "real_accounts": 0}

    @app.get("/metrics", response_class=PlainTextResponse)
    def metrics_text() -> str:
        return (
            "# Local API process counters. Not cloud telemetry.\n"
            f"identityguard_runs_total {metrics['runs']}\n"
            f"identityguard_runs_denied_total {metrics['denied']}\n"
        )

    @app.post("/v1/runs")
    async def start_run(request: Request, authorization: str | None = Header(default=None)) -> dict:
        who = principal(authorization)
        payload = await request.json()
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="body must be an object")
        try:
            view = harness.start(who, payload)
        except HarnessError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
        metrics["runs"] += 1
        if view["status"] == "denied":
            metrics["denied"] += 1
        return view

    @app.post("/v1/runs/{request_id}/resume")
    async def resume_run(
        request_id: str,
        request: Request,
        authorization: str | None = Header(default=None),
    ) -> dict:
        who = principal(authorization)
        payload = await request.json()
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="body must be an object")
        approval_id = str(payload.get("approval_id") or "")
        try:
            return harness.resume(who, request_id, approval_id)
        except HarnessError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    @app.get("/v1/runs/{request_id}")
    def get_run(request_id: str, authorization: str | None = Header(default=None)) -> dict:
        who = principal(authorization)
        try:
            return harness.view(request_id, viewer=who)
        except HarnessError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    return app
