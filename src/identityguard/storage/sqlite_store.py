"""SQLite store for local runs and tests.

Every read and write takes the tenant id chosen by the server. There is no
query that accepts a caller-supplied tenant as proof of access.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from identityguard.identity.mock_provider import load_fixtures


class SqliteStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(str(self.path), check_same_thread=False)
        self.connection.row_factory = sqlite3.Row

    def close(self) -> None:
        self.connection.close()

    def migrate(self) -> None:
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS identities (
              tenant_id TEXT NOT NULL,
              identity_id TEXT NOT NULL,
              display_name TEXT NOT NULL,
              email TEXT NOT NULL,
              status TEXT NOT NULL,
              department TEXT NOT NULL,
              PRIMARY KEY (tenant_id, identity_id)
            );
            CREATE TABLE IF NOT EXISTS evidence (
              tenant_id TEXT NOT NULL,
              evidence_id TEXT NOT NULL,
              subject_id TEXT NOT NULL,
              kind TEXT NOT NULL,
              summary TEXT NOT NULL,
              body TEXT NOT NULL,
              embedding TEXT NOT NULL,
              PRIMARY KEY (tenant_id, evidence_id)
            );
            CREATE TABLE IF NOT EXISTS runs (
              run_id TEXT PRIMARY KEY,
              tenant_id TEXT NOT NULL,
              actor TEXT NOT NULL,
              role TEXT NOT NULL,
              subject_id TEXT NOT NULL,
              status TEXT NOT NULL,
              approval_id TEXT,
              verification TEXT,
              completed INTEGER NOT NULL,
              message TEXT NOT NULL,
              proposed_action TEXT,
              evidence_json TEXT
            );
            CREATE TABLE IF NOT EXISTS approvals (
              approval_id TEXT PRIMARY KEY,
              run_id TEXT NOT NULL,
              tenant_id TEXT NOT NULL,
              requester TEXT NOT NULL,
              approver TEXT,
              approver_role TEXT,
              approver_tenant TEXT,
              decision TEXT NOT NULL,
              args_fingerprint TEXT NOT NULL,
              action_json TEXT NOT NULL,
              expires_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS effects (
              idempotency_key TEXT PRIMARY KEY,
              tenant_id TEXT NOT NULL,
              identity_id TEXT NOT NULL,
              resulting_status TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS idempotency (
              tenant_id TEXT NOT NULL,
              idem_key TEXT NOT NULL,
              run_id TEXT NOT NULL,
              PRIMARY KEY (tenant_id, idem_key)
            );
            CREATE TABLE IF NOT EXISTS memory (
              tenant_id TEXT NOT NULL,
              mem_key TEXT NOT NULL,
              payload TEXT NOT NULL,
              PRIMARY KEY (tenant_id, mem_key)
            );
            CREATE TABLE IF NOT EXISTS audit (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              tenant_id TEXT NOT NULL,
              run_id TEXT,
              action TEXT NOT NULL,
              result TEXT NOT NULL,
              actor TEXT
            );
            CREATE TABLE IF NOT EXISTS applications (
              tenant_id TEXT NOT NULL,
              identity_id TEXT NOT NULL,
              application TEXT NOT NULL,
              PRIMARY KEY (tenant_id, identity_id, application)
            );
            """
        )
        self.connection.commit()

    def seed_if_empty(self) -> None:
        count = self.connection.execute("SELECT COUNT(*) AS n FROM identities").fetchone()["n"]
        if count:
            return
        identities, events = load_fixtures()
        from identityguard.storage.pgvector import embed_text

        for row in identities:
            self.connection.execute(
                "INSERT INTO identities (tenant_id, identity_id, display_name, email, status, department) VALUES (?, ?, ?, ?, ?, ?)",
                (row["tenant_id"], row["identity_id"], row["display_name"], row["email"], row["status"], row["department"]),
            )
        for row in events:
            self.connection.execute(
                """INSERT INTO evidence
                   (tenant_id, evidence_id, subject_id, kind, summary, body, embedding)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    row["tenant_id"],
                    row["evidence_id"],
                    row["subject_id"],
                    row["kind"],
                    row["summary"],
                    row["body"],
                    json.dumps(embed_text(row["summary"] + " " + row["body"])),
                ),
            )
        self.connection.commit()

    def locate_tenant(self, identity_id: str) -> str | None:
        row = self.connection.execute(
            "SELECT tenant_id FROM identities WHERE identity_id = ?",
            (identity_id,),
        ).fetchone()
        return None if row is None else row["tenant_id"]

    def get_identity(self, tenant_id: str, identity_id: str) -> dict | None:
        row = self.connection.execute(
            "SELECT * FROM identities WHERE tenant_id = ? AND identity_id = ?",
            (tenant_id, identity_id),
        ).fetchone()
        return None if row is None else dict(row)

    def set_status(self, tenant_id: str, identity_id: str, status: str) -> bool:
        cursor = self.connection.execute(
            "UPDATE identities SET status = ? WHERE tenant_id = ? AND identity_id = ?",
            (status, tenant_id, identity_id),
        )
        self.connection.commit()
        return cursor.rowcount == 1

    def search_evidence(self, tenant_id: str, subject_id: str) -> list[dict]:
        rows = self.connection.execute(
            "SELECT evidence_id, tenant_id, subject_id, kind, summary, body FROM evidence WHERE tenant_id = ? AND subject_id = ? ORDER BY evidence_id",
            (tenant_id, subject_id),
        ).fetchall()
        return [dict(row) for row in rows]

    def search_similar(self, tenant_id: str, text: str, limit: int = 5) -> list[dict]:
        from identityguard.storage.pgvector import cosine, embed_text

        query = embed_text(text)
        rows = self.connection.execute(
            "SELECT evidence_id, tenant_id, subject_id, kind, summary, embedding FROM evidence WHERE tenant_id = ?",
            (tenant_id,),
        ).fetchall()
        ranked = []
        for row in rows:
            score = cosine(query, json.loads(row["embedding"]))
            item = dict(row)
            item.pop("embedding", None)
            item["score"] = score
            ranked.append(item)
        ranked.sort(key=lambda item: item["score"], reverse=True)
        return ranked[:limit]

    def find_idempotency(self, tenant_id: str, idem_key: str) -> str | None:
        row = self.connection.execute(
            "SELECT run_id FROM idempotency WHERE tenant_id = ? AND idem_key = ?",
            (tenant_id, idem_key),
        ).fetchone()
        return None if row is None else row["run_id"]

    def save_idempotency(self, tenant_id: str, idem_key: str, run_id: str) -> None:
        self.connection.execute(
            "INSERT INTO idempotency (tenant_id, idem_key, run_id) VALUES (?, ?, ?)",
            (tenant_id, idem_key, run_id),
        )
        self.connection.commit()

    def save_run(self, **fields) -> None:
        self.connection.execute(
            """INSERT INTO runs
               (run_id, tenant_id, actor, role, subject_id, status, approval_id, verification, completed, message, proposed_action, evidence_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                fields["run_id"],
                fields["tenant_id"],
                fields["actor"],
                fields["role"],
                fields["subject_id"],
                fields["status"],
                fields.get("approval_id"),
                fields.get("verification"),
                1 if fields.get("completed") else 0,
                fields.get("message", ""),
                json.dumps(fields.get("proposed_action")),
                json.dumps(fields.get("evidence") or []),
            ),
        )
        self.connection.commit()

    def update_run(self, run_id: str, tenant_id: str, **fields) -> None:
        current = self.get_run(tenant_id, run_id)
        if current is None:
            raise KeyError(run_id)
        merged = {**current, **fields}
        self.connection.execute(
            """UPDATE runs SET status = ?, approval_id = ?, verification = ?, completed = ?, message = ?, proposed_action = ?, evidence_json = ?
               WHERE run_id = ? AND tenant_id = ?""",
            (
                merged["status"],
                merged.get("approval_id"),
                merged.get("verification"),
                1 if merged.get("completed") else 0,
                merged.get("message") or "",
                json.dumps(merged.get("proposed_action")),
                json.dumps(merged.get("evidence") or []),
                run_id,
                tenant_id,
            ),
        )
        self.connection.commit()

    def get_run(self, tenant_id: str, run_id: str) -> dict | None:
        row = self.connection.execute(
            "SELECT * FROM runs WHERE tenant_id = ? AND run_id = ?",
            (tenant_id, run_id),
        ).fetchone()
        if row is None:
            return None
        item = dict(row)
        item["completed"] = bool(item["completed"])
        item["proposed_action"] = json.loads(item.pop("proposed_action") or "null")
        item["evidence"] = json.loads(item.pop("evidence_json") or "[]")
        return item

    def ensure_approval(self, **fields) -> None:
        existing = self.connection.execute(
            "SELECT approval_id FROM approvals WHERE approval_id = ? AND tenant_id = ?",
            (fields["approval_id"], fields["tenant_id"]),
        ).fetchone()
        if existing:
            return
        self.connection.execute(
            """INSERT INTO approvals
               (approval_id, run_id, tenant_id, requester, approver, approver_role, approver_tenant, decision, args_fingerprint, action_json, expires_at)
               VALUES (?, ?, ?, ?, NULL, NULL, NULL, 'pending', ?, ?, ?)""",
            (
                fields["approval_id"],
                fields["run_id"],
                fields["tenant_id"],
                fields["requester"],
                fields["args_fingerprint"],
                json.dumps(fields["action"]),
                fields["expires_at"],
            ),
        )
        self.connection.commit()

    def get_approval(self, tenant_id: str, approval_id: str) -> dict | None:
        row = self.connection.execute(
            "SELECT * FROM approvals WHERE tenant_id = ? AND approval_id = ?",
            (tenant_id, approval_id),
        ).fetchone()
        if row is None:
            return None
        item = dict(row)
        item["action"] = json.loads(item.pop("action_json"))
        return item

    def decide_approval(self, tenant_id: str, approval_id: str, *, decision: str, approver: str, approver_role: str, approver_tenant: str) -> bool:
        cursor = self.connection.execute(
            """UPDATE approvals
               SET decision = ?, approver = ?, approver_role = ?, approver_tenant = ?
               WHERE tenant_id = ? AND approval_id = ? AND decision = 'pending'""",
            (decision, approver, approver_role, approver_tenant, tenant_id, approval_id),
        )
        self.connection.commit()
        return cursor.rowcount == 1

    def get_effect(self, idempotency_key: str) -> dict | None:
        row = self.connection.execute(
            "SELECT * FROM effects WHERE idempotency_key = ?",
            (idempotency_key,),
        ).fetchone()
        return None if row is None else dict(row)

    def save_effect(self, idempotency_key: str, tenant_id: str, identity_id: str, resulting_status: str) -> None:
        self.connection.execute(
            "INSERT INTO effects (idempotency_key, tenant_id, identity_id, resulting_status) VALUES (?, ?, ?, ?)",
            (idempotency_key, tenant_id, identity_id, resulting_status),
        )
        self.connection.commit()

    def count_effects(self, identity_id: str) -> int:
        row = self.connection.execute(
            "SELECT COUNT(*) AS n FROM effects WHERE identity_id = ?",
            (identity_id,),
        ).fetchone()
        return int(row["n"])

    def write_memory(self, tenant_id: str, key: str, payload: dict) -> None:
        self.connection.execute(
            "INSERT OR REPLACE INTO memory (tenant_id, mem_key, payload) VALUES (?, ?, ?)",
            (tenant_id, key, json.dumps(payload)),
        )
        self.connection.commit()

    def read_memory(self, tenant_id: str, key: str) -> dict | None:
        row = self.connection.execute(
            "SELECT payload FROM memory WHERE tenant_id = ? AND mem_key = ?",
            (tenant_id, key),
        ).fetchone()
        return None if row is None else json.loads(row["payload"])

    def audit(self, *, tenant_id: str, run_id: str | None, action: str, result: str, actor: str | None) -> None:
        self.connection.execute(
            "INSERT INTO audit (tenant_id, run_id, action, result, actor) VALUES (?, ?, ?, ?, ?)",
            (tenant_id, run_id, action, result, actor),
        )
        self.connection.commit()

    def list_identities(self, tenant_id: str) -> list[dict]:
        rows = self.connection.execute(
            "SELECT identity_id, status, department FROM identities WHERE tenant_id = ? ORDER BY identity_id",
            (tenant_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def save_application(self, tenant_id: str, identity_id: str, application: str) -> None:
        self.connection.execute(
            "INSERT OR IGNORE INTO applications (tenant_id, identity_id, application) VALUES (?, ?, ?)",
            (tenant_id, identity_id, application),
        )
        self.connection.commit()

    def list_applications(self, tenant_id: str, identity_id: str) -> list[str]:
        rows = self.connection.execute(
            "SELECT application FROM applications WHERE tenant_id = ? AND identity_id = ? ORDER BY application",
            (tenant_id, identity_id),
        ).fetchall()
        return [row["application"] for row in rows]

    def audit_text(self, tenant_id: str) -> str:
        rows = self.connection.execute(
            "SELECT action, result, actor, run_id FROM audit WHERE tenant_id = ?",
            (tenant_id,),
        ).fetchall()
        return "\n".join(json.dumps(dict(row), sort_keys=True) for row in rows)
