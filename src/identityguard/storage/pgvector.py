"""Tenant-scoped similarity.

SQLite ranks a deterministic 8-float vector in process. PostgreSQL uses the
same vector with pgvector and a tenant setting. The vector is a fixture, not
an embedding model.
"""

from __future__ import annotations

import hashlib
import math


def embed_text(text: str) -> list[float]:
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    values = [((digest[index] / 127.5) - 1.0) for index in range(8)]
    norm = math.sqrt(sum(value * value for value in values)) or 1.0
    return [value / norm for value in values]


def cosine(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right))


PGVECTOR_SCHEMA = """
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS evidence_embeddings (
  tenant_id TEXT NOT NULL,
  evidence_id TEXT NOT NULL,
  embedding vector(8) NOT NULL,
  PRIMARY KEY (tenant_id, evidence_id)
);
ALTER TABLE evidence_embeddings ENABLE ROW LEVEL SECURITY;
ALTER TABLE evidence_embeddings FORCE ROW LEVEL SECURITY;
"""

PGVECTOR_POLICY = """
CREATE POLICY evidence_embeddings_tenant ON evidence_embeddings
  USING (tenant_id = current_setting('identityguard.tenant', true))
  WITH CHECK (tenant_id = current_setting('identityguard.tenant', true));
"""
