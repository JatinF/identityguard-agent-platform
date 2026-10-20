"""FastAPI application.

uvicorn identityguard.api.main:app
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, Header, Request
from fastapi.responses import Response

from identityguard import __version__
from identityguard.api.agents import principal_or_401, router as agents_router
from identityguard.api.approvals import router as approvals_router
from identityguard.api.identities import router as identities_router
from identityguard.evaluations.runner import build_report
from identityguard.harness.recovery import open_service
from identityguard.telemetry.metrics import build_metrics, render_metrics
from identityguard.telemetry.tracing import build_tracer
from prometheus_client import CONTENT_TYPE_LATEST


def create_app(service=None) -> FastAPI:
    app = FastAPI(title="IdentityGuard AI", version=__version__)
    if service is None:
        root = Path(os.environ.get("IG_STATE_DIR", "var"))
        service = open_service(root)
    registry, runs, approvals = build_metrics()
    tracer, exporter = build_tracer()
    app.state.service = service
    app.state.registry = registry
    app.state.runs = runs
    app.state.approvals = approvals
    app.state.tracer = tracer
    app.state.exporter = exporter

    @app.middleware("http")
    async def trace_request(request: Request, call_next):
        with app.state.tracer.start_as_current_span(f"{request.method} {request.url.path}"):
            return await call_next(request)

    @app.get("/healthz")
    def healthz() -> dict:
        return {"status": "ok", "real_accounts": 0, "model_provider": os.environ.get("MODEL_PROVIDER", "mock")}

    @app.get("/metrics")
    def metrics() -> Response:
        return Response(content=render_metrics(app.state.registry), media_type=CONTENT_TYPE_LATEST)

    @app.get("/v1/evaluations/report")
    def evaluations_report(authorization: str | None = Header(default=None)) -> dict:
        principal_or_401(authorization)
        return build_report()

    app.include_router(agents_router)
    app.include_router(approvals_router)
    app.include_router(identities_router)
    return app


app = create_app()
