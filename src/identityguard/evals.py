"""Replay the golden identity cases.

Each case opens a fresh directory and a fresh checkpoint. The same case run
twice yields the same status. Free-text fixtures are not copied into the report.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from identityguard.auth import authenticate
from identityguard.directory import Directory
from identityguard.harness import HarnessError, open_harness
from identityguard.memory import TenantMemory

ROOT = Path(__file__).resolve().parents[2]
CASES = ROOT / "evals" / "cases.json"


def run_suite() -> list[dict]:
    payload = json.loads(CASES.read_text(encoding="utf-8"))
    if payload.get("evidence_class") != "EXAMPLE":
        raise ValueError("eval cases must be tagged EXAMPLE")
    return [_run_case(case) for case in payload["cases"]]


def render_eval(results: list[dict] | None = None) -> str:
    results = results if results is not None else run_suite()
    passed = sum(1 for item in results if item["passed"])
    lines = [
        "# Replayable evaluation report",
        "",
        f"Cases passed: {passed} of {len(results)}.",
        "",
        "These rows are the local harness. They are not an AWS Step Functions execution and they are not a hosted-model trace.",
        "",
        "| Case | Passed | Status |",
        "| --- | --- | --- |",
    ]
    for item in results:
        flag = "yes" if item["passed"] else "no"
        lines.append(f"| {item['id']} | {flag} | {item['status']} |")
    lines.append("")
    return "\n".join(lines)


def recovery_check() -> bool:
    """Close the checkpoint database and resume the same thread in a new process-shaped harness."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        first = open_harness(root / "runs.sqlite", root / "audit.jsonl")
        try:
            operator = authenticate("Bearer dev-operator-a")
            paused = first.start(
                operator,
                {
                    "request_id": "SYN-REQ-900",
                    "operation": "disable-account",
                    "target": "SYN-USER-014",
                },
            )
            if paused["status"] != "awaiting-approval" or paused["mutated"]:
                return False
        finally:
            first.close()
        second = open_harness(root / "runs.sqlite", root / "audit.jsonl")
        try:
            approver = authenticate("Bearer dev-approver-a")
            done = second.resume(approver, "SYN-REQ-900", "APR-900")
            account = second.directory.get("tenant-a", "SYN-USER-014")
            return bool(
                done["status"] == "verified"
                and done["verified"]
                and account is not None
                and account["status"] == "disabled"
            )
        finally:
            second.close()


def isolation_check() -> bool:
    memory = TenantMemory()
    memory.write("tenant-a", "run:SYN-REQ-1", {"marker": "TENANT-A-ONLY"})
    if memory.read("tenant-b", "run:SYN-REQ-1") is not None:
        return False
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        harness = open_harness(root / "runs.sqlite", root / "audit.jsonl")
        try:
            harness.audit.write(
                action="run",
                result="verified",
                tenant="tenant-b",
                actor="SYN-B-MARKER",
                request_id="SYN-REQ-001",
            )
            paused = harness.start(
                authenticate("Bearer dev-operator-a"),
                {
                    "request_id": "SYN-REQ-910",
                    "operation": "export-audit",
                    "target": "SYN-AUDIT",
                },
            )
            if paused["status"] != "awaiting-approval":
                return False
            done = harness.resume(authenticate("Bearer dev-approver-a"), "SYN-REQ-910", "APR-910")
            blob = json.dumps(done)
            other = Directory.from_seed().fingerprint("tenant-b")
            return bool(
                done["status"] == "verified"
                and done["verified"]
                and not done["mutated"]
                and "SYN-B-MARKER" not in blob
                and harness.directory.fingerprint("tenant-b") == other
            )
        finally:
            harness.close()


def _run_case(case: dict) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        harness = open_harness(root / "runs.sqlite", root / "audit.jsonl")
        try:
            before_b = harness.directory.fingerprint("tenant-b")
            who = authenticate(f"Bearer {case['token']}")
            view = harness.start(who, case["request"])
            resume_code = None
            if case.get("resume_token"):
                approver = authenticate(f"Bearer {case['resume_token']}")
                try:
                    view = harness.resume(approver, case["request"]["request_id"], case["approval_id"])
                    resume_code = 200
                except HarnessError as exc:
                    resume_code = exc.status_code
                    view = harness.view(case["request"]["request_id"])
            expect = case["expect"]
            mismatches = []
            for key, value in expect.items():
                if key == "role_present":
                    if value not in view["target_roles"]:
                        mismatches.append(key)
                elif view.get(key) != value:
                    mismatches.append(f"{key}={view.get(key)!s}")
            if case.get("expect_resume_status") is not None and resume_code != case["expect_resume_status"]:
                mismatches.append(f"resume={resume_code}")
            if harness.directory.fingerprint("tenant-b") != before_b:
                mismatches.append("tenant-b changed")
            phrase = case.get("must_not_appear")
            if phrase:
                audit_blob = harness.audit.path.read_text(encoding="utf-8") if harness.audit.path.is_file() else ""
                state = harness.graph.get_state({"configurable": {"thread_id": case["request"]["request_id"]}}).values
                remembered = harness.memory.read(str(view["tenant"]), f"run:{view['request_id']}")
                visible = "\n".join([audit_blob, json.dumps(dict(state), default=str), json.dumps(remembered), json.dumps(view)])
                if phrase in visible:
                    mismatches.append("phrase leaked")
            if case["id"] == "disable-approved":
                try:
                    harness.start(who, case["request"])
                    mismatches.append("duplicate start accepted")
                except HarnessError as exc:
                    if exc.status_code != 409:
                        mismatches.append("duplicate start code")
                if harness.view(case["request"]["request_id"])["target_status"] != "disabled":
                    mismatches.append("duplicate start changed the account again")
            return {
                "id": case["id"],
                "passed": not mismatches,
                "status": str(view["status"]),
                "detail": ", ".join(mismatches),
            }
        finally:
            harness.close()
