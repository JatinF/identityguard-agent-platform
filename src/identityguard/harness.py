"""Start and resume runs.

The harness is the supported entry point. It copies the tenant and the role
from the principal, drops free text before the graph sees it, and refuses a
second start of the same request id.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from identityguard.audit import AuditLog
from identityguard.auth import Principal
from identityguard.directory import Directory
from identityguard.graph import build_graph
from identityguard.memory import TenantMemory
from identityguard.policy import forbidden_keys


class HarnessError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


class Harness:
    def __init__(self, graph, directory: Directory, memory: TenantMemory, audit: AuditLog, connection):
        self.graph = graph
        self.directory = directory
        self.memory = memory
        self.audit = audit
        self.connection = connection

    def close(self) -> None:
        self.connection.close()

    def start(self, principal: Principal, request: dict) -> dict:
        banned = forbidden_keys(request)
        if banned:
            self.audit.write(action="run", result="deny", tenant=principal.tenant, actor=principal.token_name, detail="credential material")
            raise HarnessError(422, "credential material is not accepted")
        request_id = str(request.get("request_id") or "")
        config = _config(request_id)
        existing = self.graph.get_state(config)
        if existing.values:
            raise HarnessError(409, "run already exists")
        initial = {
            "request_id": request_id,
            "tenant": principal.tenant,
            "actor": principal.token_name,
            "role": principal.role,
            "operation": str(request.get("operation") or ""),
            "target": str(request.get("target") or ""),
            "role_name": str(request.get("role_name") or ""),
            "approval": None,
        }
        self.graph.invoke(initial, config)
        return self.view(request_id)

    def resume(self, principal: Principal, request_id: str, approval_id: str) -> dict:
        config = _config(request_id)
        snapshot = self.graph.get_state(config)
        values = snapshot.values or {}
        if not values:
            raise HarnessError(404, "run not found")
        if values.get("tenant") != principal.tenant:
            raise HarnessError(404, "run not found")
        if not snapshot.next:
            raise HarnessError(409, "run is not waiting")
        if principal.role != "approver":
            raise HarnessError(403, "approver required")
        if principal.token_name == values.get("actor"):
            raise HarnessError(403, "self-approval denied")
        if not str(approval_id).startswith("APR-"):
            raise HarnessError(422, "approval id must start with APR-")
        payload = {
            "approval_id": approval_id,
            "approver": principal.token_name,
            "approver_role": principal.role,
            "tenant": principal.tenant,
            "request_id": request_id,
        }
        self.graph.invoke(Command(resume=payload), config)
        return self.view(request_id)

    def view(self, request_id: str, *, viewer: Principal | None = None) -> dict:
        snapshot = self.graph.get_state(_config(request_id))
        values = snapshot.values or {}
        if not values:
            raise HarnessError(404, "run not found")
        if viewer is not None and values.get("tenant") != viewer.tenant:
            raise HarnessError(404, "run not found")
        interrupted = bool(snapshot.next)
        tenant = str(values.get("tenant") or "")
        target = str(values.get("target") or "")
        account = self.directory.get(tenant, target) if target.startswith("SYN-USER-") else None
        before = values.get("fingerprint_before")
        after = self.directory.fingerprint(tenant) if tenant else ""
        tool_result = values.get("tool_result")
        public_tool = None
        if isinstance(tool_result, dict):
            public_tool = {key: value for key, value in tool_result.items() if key != "idempotent_replay"}
            public_tool["idempotent_replay"] = bool(tool_result.get("idempotent_replay"))
        return {
            "request_id": values.get("request_id"),
            "tenant": tenant,
            "actor": values.get("actor"),
            "operation": values.get("operation"),
            "target": target,
            "decision": values.get("decision"),
            "status": "awaiting-approval" if interrupted else values.get("status"),
            "verified": False if interrupted else bool(values.get("verified")),
            "mutated": before is not None and after != before,
            "reasons": list(values.get("deny_reasons") or []),
            "target_status": None if account is None else account["status"],
            "target_roles": [] if account is None else account["roles"],
            "tool_result": public_tool,
            "interrupted": interrupted,
        }


def open_harness(db_path: Path, audit_path: Path, *, force_tool_down: bool = False) -> Harness:
    directory = Directory.from_seed()
    memory = TenantMemory()
    audit = AuditLog(audit_path)
    connection = sqlite3.connect(str(db_path), check_same_thread=False)
    saver = SqliteSaver(connection)
    if hasattr(saver, "setup"):
        saver.setup()
    graph = build_graph(directory, memory, audit, saver, force_tool_down=force_tool_down)
    return Harness(graph, directory, memory, audit, connection)


def _config(request_id: str) -> dict:
    return {"configurable": {"thread_id": request_id}}
