"""Bound evidence before it is stored on the checkpoint.

Evidence ids are kept. A long body is replaced by its summary so a large
event does not grow the checkpoint without a limit.
"""

from __future__ import annotations


def compact_evidence(rows: list[dict], budget: int = 500) -> list[dict]:
    compacted = []
    for row in rows:
        body = str(row.get("body") or "")
        if len(body) > budget:
            body = str(row.get("summary") or "")
        compacted.append(
            {
                "evidence_id": row["evidence_id"],
                "tenant_id": row["tenant_id"],
                "subject_id": row["subject_id"],
                "kind": row["kind"],
                "summary": row["summary"],
                "body": body,
            }
        )
    return compacted
