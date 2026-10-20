"""PostgreSQL store with row-level security.

The application sets identityguard.tenant inside the transaction. Policies are
forced for the table owner. A superuser still bypasses row-level security, and
the Docker database user is a superuser, so data statements switch to
identityguard_app with SET LOCAL ROLE. This module is used when DATABASE_URL
is set.
"""

from __future__ import annotations

import json

from identityguard.identity.mock_provider import load_fixtures
from identityguard.storage.pgvector import PGVECTOR_POLICY, PGVECTOR_SCHEMA, embed_text

SCHEMA = """
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
  PRIMARY KEY (tenant_id, evidence_id)
);
ALTER TABLE identities ENABLE ROW LEVEL SECURITY;
ALTER TABLE identities FORCE ROW LEVEL SECURITY;
ALTER TABLE evidence ENABLE ROW LEVEL SECURITY;
ALTER TABLE evidence FORCE ROW LEVEL SECURITY;
"""

POLICIES = """
CREATE POLICY identities_tenant ON identities
  USING (tenant_id = current_setting('identityguard.tenant', true))
  WITH CHECK (tenant_id = current_setting('identityguard.tenant', true));
CREATE POLICY evidence_tenant ON evidence
  USING (tenant_id = current_setting('identityguard.tenant', true))
  WITH CHECK (tenant_id = current_setting('identityguard.tenant', true));
"""


class PostgresStore:
    def __init__(self, dsn: str):
        import psycopg
        from psycopg.rows import dict_row

        self._psycopg = psycopg
        self._dict_row = dict_row
        self.dsn = dsn

    def connect(self):
        return self._psycopg.connect(self.dsn, row_factory=self._dict_row)

    def migrate(self) -> None:
        with self.connect() as conn:
            conn.execute(SCHEMA)
            conn.execute(PGVECTOR_SCHEMA)
            self._ensure_policy(conn, "identities_tenant", "CREATE POLICY identities_tenant ON identities USING (tenant_id = current_setting('identityguard.tenant', true)) WITH CHECK (tenant_id = current_setting('identityguard.tenant', true))")
            self._ensure_policy(conn, "evidence_tenant", "CREATE POLICY evidence_tenant ON evidence USING (tenant_id = current_setting('identityguard.tenant', true)) WITH CHECK (tenant_id = current_setting('identityguard.tenant', true))")
            self._ensure_policy(conn, "evidence_embeddings_tenant", PGVECTOR_POLICY)
            conn.execute(
                """
                DO $$
                BEGIN
                  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'identityguard_app') THEN
                    CREATE ROLE identityguard_app NOLOGIN NOSUPERUSER NOBYPASSRLS;
                  END IF;
                END $$;
                """
            )
            conn.execute("GRANT USAGE ON SCHEMA public TO identityguard_app")
            conn.execute(
                "GRANT SELECT, INSERT, UPDATE, DELETE ON identities, evidence, evidence_embeddings TO identityguard_app"
            )
            conn.commit()

    def _ensure_policy(self, conn, name: str, statement: str) -> None:
        row = conn.execute("SELECT 1 FROM pg_policies WHERE policyname = %s", (name,)).fetchone()
        if row is None:
            conn.execute(statement)

    def seed_if_empty(self) -> None:
        identities, events = load_fixtures()
        with self.connect() as conn:
            self._assume_app_role(conn)
            for row in identities:
                self._set_tenant(conn, row["tenant_id"])
                conn.execute(
                    """INSERT INTO identities (tenant_id, identity_id, display_name, email, status, department)
                       VALUES (%s, %s, %s, %s, %s, %s)
                       ON CONFLICT DO NOTHING""",
                    (row["tenant_id"], row["identity_id"], row["display_name"], row["email"], row["status"], row["department"]),
                )
            for row in events:
                self._set_tenant(conn, row["tenant_id"])
                conn.execute(
                    """INSERT INTO evidence (tenant_id, evidence_id, subject_id, kind, summary, body)
                       VALUES (%s, %s, %s, %s, %s, %s)
                       ON CONFLICT DO NOTHING""",
                    (row["tenant_id"], row["evidence_id"], row["subject_id"], row["kind"], row["summary"], row["body"]),
                )
                vector = "[" + ",".join(str(value) for value in embed_text(row["summary"] + " " + row["body"])) + "]"
                conn.execute(
                    """INSERT INTO evidence_embeddings (tenant_id, evidence_id, embedding)
                       VALUES (%s, %s, %s::vector)
                       ON CONFLICT DO NOTHING""",
                    (row["tenant_id"], row["evidence_id"], vector),
                )
            conn.commit()

    def visible_identity_ids(self, tenant_id: str) -> list[str]:
        with self.connect() as conn:
            self._assume_app_role(conn)
            self._set_tenant(conn, tenant_id)
            rows = conn.execute("SELECT identity_id FROM identities ORDER BY identity_id").fetchall()
            return [row["identity_id"] for row in rows]

    def visible_without_tenant(self) -> list[str]:
        with self.connect() as conn:
            self._assume_app_role(conn)
            conn.execute("SELECT set_config('identityguard.tenant', '', true)")
            rows = conn.execute("SELECT identity_id FROM identities").fetchall()
            return [row["identity_id"] for row in rows]

    @staticmethod
    def _assume_app_role(conn) -> None:
        conn.execute("SET LOCAL ROLE identityguard_app")

    @staticmethod
    def _set_tenant(conn, tenant_id: str) -> None:
        conn.execute("SELECT set_config('identityguard.tenant', %s, true)", (tenant_id,))
