"""Start, resume, and decide investigation runs.

The tenant and the role come from the authenticated principal. A tenant field
on the body is ignored. Resume loads the checkpoint and the approval row, then
runs the same reauthorize check the graph uses before any write.
"""

from __future__ import annotations

import os
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from langgraph.types import Command

from identityguard.harness.checkpoints import open_checkpointer
from identityguard.harness.graph import MESSAGES, build_graph
from identityguard.identity.tools import IdentityTools
from identityguard.models.hosted import build_model
from identityguard.principals import Principal
from identityguard.storage.sqlite_store import SqliteStore

KEY_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
FORBIDDEN_KEYS = frozenset({"password", "secret", "api_key", "ssn", "private_key"})


class ServiceError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


class Clock:
    """Injectable clock. Tests move it to expire an approval."""

    def __init__(self, moment: datetime | None = None):
        if moment is None:
            moment = datetime.now(timezone.utc).replace(microsecond=0)
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        self.moment = moment

    def now(self) -> datetime:
        return self.moment

    def advance(self, seconds: int) -> None:
        self.moment = self.moment + timedelta(seconds=seconds)


class AgentService:
    def __init__(self, store: SqliteStore, graph, clock: Clock, checkpoint_connection, tools: IdentityTools):
        self.store = store
        self.graph = graph
        self.clock = clock
        self.checkpoint_connection = checkpoint_connection
        self.tools = tools

    def close(self) -> None:
        self.store.close()
        self.checkpoint_connection.close()

    def start(self, principal: Principal, *, subject_id: str, goal: str, idempotency_key: str, body_tenant: str | None = None) -> dict:
        del body_tenant  # Never a proof of access.
        if not KEY_PATTERN.fullmatch(idempotency_key or ""):
            raise ServiceError(400, "idempotency key is missing or invalid")
        if not subject_id or not str(subject_id).startswith("SYN-"):
            raise ServiceError(400, "subject_id must be a synthetic identity id")
        existing = self.store.find_idempotency(principal.tenant_id, idempotency_key)
        if existing:
            return self.view(principal, existing)
        run_id = f"SYN-RUN-{principal.tenant_id}-{idempotency_key}"
        try:
            self.store.save_run(
                run_id=run_id,
                tenant_id=principal.tenant_id,
                actor=principal.token_name,
                role=principal.role,
                subject_id=subject_id,
                status="RUNNING",
                completed=False,
                message="",
            )
            self.store.save_idempotency(principal.tenant_id, idempotency_key, run_id)
        except sqlite3.IntegrityError as exc:
            raise ServiceError(409, "idempotency key is already in use") from exc
        self.graph.invoke(_initial(principal, run_id, subject_id, goal), _config(run_id))
        return self.view(principal, run_id)

    def view(self, principal: Principal, run_id: str) -> dict:
        row = self.store.get_run(principal.tenant_id, run_id)
        if row is None:
            raise ServiceError(404, "run not found")
        return _public_view(self.store, row)

    def resume(self, principal: Principal, run_id: str) -> dict:
        row = self.store.get_run(principal.tenant_id, run_id)
        if row is None:
            raise ServiceError(404, "run not found")
        config = _config(run_id)
        snapshot = self.graph.get_state(config)
        if not snapshot.next:
            return _public_view(self.store, row)
        approval_id = row.get("approval_id")
        record = self.store.get_approval(principal.tenant_id, approval_id) if approval_id else None
        if record is None:
            return _public_view(self.store, row)
        if record.get("decision") == "pending" and not _expired(record, self.clock.now()):
            return _public_view(self.store, row)
        self.graph.invoke(Command(resume={"approval_id": approval_id}), config)
        return self.view(principal, run_id)

    def decide(self, principal: Principal, approval_id: str, decision: str) -> dict:
        if principal.role != "approver":
            raise ServiceError(403, "approver role required")
        if decision not in {"approved", "rejected"}:
            raise ServiceError(400, "decision must be approved or rejected")
        record = self.store.get_approval(principal.tenant_id, approval_id)
        if record is None:
            raise ServiceError(404, "approval not found")
        if principal.token_name == record.get("requester"):
            raise ServiceError(403, "self-approval is not allowed")
        if record.get("decision") != "pending":
            return self.view(principal, record["run_id"])
        self.store.decide_approval(
            principal.tenant_id,
            approval_id,
            decision=decision,
            approver=principal.token_name,
            approver_role=principal.role,
            approver_tenant=principal.tenant_id,
        )
        self.store.audit(
            tenant_id=principal.tenant_id,
            run_id=record["run_id"],
            action="approval",
            result=decision,
            actor=principal.token_name,
        )
        self.graph.invoke(Command(resume={"approval_id": approval_id}), _config(record["run_id"]))
        return self.view(principal, record["run_id"])

    def identity(self, principal: Principal, identity_id: str) -> dict:
        row = self.store.get_identity(principal.tenant_id, identity_id)
        if row is None:
            raise ServiceError(404, "identity not found")
        return {
            "identity_id": row["identity_id"],
            "tenant_id": row["tenant_id"],
            "display_name": row["display_name"],
            "email": row["email"],
            "status": row["status"],
            "department": row["department"],
        }


def open_service(
    directory: Path,
    *,
    model=None,
    skip_write: bool = False,
    clock: Clock | None = None,
    ttl_seconds: int = 3600,
    max_attempts: int = 3,
) -> AgentService:
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    store = SqliteStore(directory / "app.sqlite")
    store.migrate()
    store.seed_if_empty()
    saver, connection = open_checkpointer(directory / "checkpoints.sqlite")
    clock = clock or Clock()
    tools = IdentityTools(store, skip_write=skip_write)
    if model is None:
        model = build_model(os.environ.get("MODEL_PROVIDER", "mock"))
    graph = build_graph(
        store,
        tools,
        model,
        clock,
        saver,
        ttl_seconds=ttl_seconds,
        max_attempts=max_attempts,
    )
    return AgentService(store, graph, clock, connection, tools)


def forbidden_keys(payload: dict) -> list[str]:
    found: list[str] = []

    def walk(value) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if str(key).lower() in FORBIDDEN_KEYS:
                    found.append(str(key))
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(payload)
    return found


def _initial(principal: Principal, run_id: str, subject_id: str, goal: str) -> dict:
    return {
        "run_id": run_id,
        "tenant_id": principal.tenant_id,
        "actor": principal.token_name,
        "role": principal.role,
        "goal": goal,
        "subject_id": subject_id,
        "status": "RUNNING",
    }


def _config(run_id: str) -> dict:
    return {"configurable": {"thread_id": run_id}}


def _expired(record: dict, now: datetime) -> bool:
    expires_at = datetime.fromisoformat(str(record["expires_at"]).replace("Z", "+00:00"))
    return expires_at <= now


def _public_view(store: SqliteStore, row: dict) -> dict:
    identity = store.get_identity(row["tenant_id"], row["subject_id"])
    status = row["status"]
    completed = bool(row["completed"]) and status == "VERIFIED"
    message = row.get("message") or MESSAGES.get(status, "Workflow stopped. No write occurred.")
    if status != "VERIFIED":
        message = MESSAGES.get(status, "Workflow stopped. No write occurred.")
    return {
        "run_id": row["run_id"],
        "tenant_id": row["tenant_id"],
        "actor": row["actor"],
        "role": row["role"],
        "subject_id": row["subject_id"],
        "status": status,
        "approval_id": row.get("approval_id"),
        "verification": row.get("verification"),
        "completed": completed,
        "completion_claimed": completed,
        "message": message,
        "proposed_action": row.get("proposed_action"),
        "evidence": row.get("evidence") or [],
        "account_status": None if identity is None else identity["status"],
    }
