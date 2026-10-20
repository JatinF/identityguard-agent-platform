"""Token map for development and tests.

Production replaces this map with the site identity provider. The tenant and
the role come from the token. The request body cannot select them.
"""

from __future__ import annotations

from dataclasses import dataclass


class AuthError(PermissionError):
    pass


@dataclass(frozen=True)
class Principal:
    token_name: str
    tenant: str
    role: str


DEV_TOKENS = {
    "dev-reader-a": {"name": "dev-reader-a", "tenant": "tenant-a", "role": "reader"},
    "dev-operator-a": {"name": "dev-operator-a", "tenant": "tenant-a", "role": "operator"},
    "dev-approver-a": {"name": "dev-approver-a", "tenant": "tenant-a", "role": "approver"},
    "dev-operator-b": {"name": "dev-operator-b", "tenant": "tenant-b", "role": "operator"},
    "dev-approver-b": {"name": "dev-approver-b", "tenant": "tenant-b", "role": "approver"},
}


def authenticate(header: str | None, tokens: dict[str, dict[str, str]] | None = None) -> Principal:
    token_map = tokens if tokens is not None else DEV_TOKENS
    if not header or not header.lower().startswith("bearer "):
        raise AuthError("missing bearer token")
    token = header.split(" ", 1)[1].strip()
    record = token_map.get(token)
    if not record:
        raise AuthError("unknown token")
    role = record.get("role", "")
    tenant = record.get("tenant", "")
    if role not in {"reader", "operator", "approver"} or not tenant:
        raise AuthError("token is missing a tenant or a role")
    return Principal(token_name=record.get("name", "unnamed"), tenant=tenant, role=role)
