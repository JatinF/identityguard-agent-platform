"""Deployment acceptance report.

Software gates are checks this module can execute. AWS and hosted-model gates
stay not-run until an evidence file names an execution and a log. The
production decision is NO-GO while any required row is not a measured pass.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AWS_EVIDENCE = ROOT / "benchmarks" / "aws-evidence.json"

GATES = (
    "stepfunctions-execution",
    "idp-provider-binding",
    "hosted-model-run",
)


def gate_rows(evidence_path: Path | None = None) -> list[dict]:
    path = evidence_path if evidence_path is not None else AWS_EVIDENCE
    records = []
    if path.is_file():
        payload = json.loads(path.read_text(encoding="utf-8"))
        records = payload.get("records", [])
    by_id = {record.get("test_id"): record for record in records}
    rows = []
    for test_id in GATES:
        record = by_id.get(test_id)
        if (
            record
            and record.get("evidence_class") == "MEASURED"
            and record.get("result") == "pass"
            and record.get("serials")
            and record.get("log")
        ):
            rows.append({"test_id": test_id, "status": "pass"})
        elif record:
            rows.append({"test_id": test_id, "status": "fail"})
        else:
            rows.append({"test_id": test_id, "status": "not-run"})
    return rows


def software_checks() -> bool:
    from identityguard.evals import isolation_check, recovery_check, run_suite

    results = run_suite()
    if not results or any(not item["passed"] for item in results):
        return False
    return recovery_check() and isolation_check()


def build_report(software_ok: bool, evidence_path: Path | None = None) -> dict:
    rows = gate_rows(evidence_path)
    external_go = all(row["status"] == "pass" for row in rows)
    decision = "GO" if software_ok and external_go else "NO-GO"
    if decision == "GO":
        reason = "Software slice passed and AWS evidence is filed."
    else:
        reason = (
            "Production identity operations stay NO-GO until every external gate is a MEASURED pass "
            "with an execution identifier and a log. A passing local replay is not that evidence."
        )
    return {
        "decision": decision,
        "software_slice": "pass" if software_ok else "fail",
        "gate_rows": rows,
        "reason": reason,
    }


def render_markdown(report: dict) -> str:
    lines = [
        "# Deployment acceptance report",
        "",
        f"**Decision: {report['decision']}**",
        "",
        f"Software vertical slice: {report['software_slice']}.",
        "",
        report["reason"],
        "",
        "| External gate | Status |",
        "| --- | --- |",
    ]
    for row in report["gate_rows"]:
        lines.append(f"| {row['test_id']} | {row['status']} |")
    lines.extend(
        [
            "",
            "Step Functions, the site identity provider, and any hosted model are rows in this table. The local replay report does not fill them.",
            "",
        ]
    )
    return "\n".join(lines)
