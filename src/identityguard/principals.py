"""Token map for the local demo and the tests.

A deployment replaces this map with the site identity provider. Tenant and
role come from the token. A tenant field on the request body is not consulted.
"""

from __future__ import annotations

from dataclasses import dataclass


class AuthError(PermissionError):
    pass


@dataclass(frozen=True)
class Principal:
    token_name: str
    tenant_id: str
    role: str


DEV_TOKENS = {
    "dev-reader-a": {"name": "dev-reader-a", "tenant_id": "tenant-a", "role": "reader"},
    "dev-operator-a": {"name": "dev-operator-a", "tenant_id": "tenant-a", "role": "operator"},
    "dev-approver-a": {"name": "dev-approver-a", "tenant_id": "tenant-a", "role": "approver"},
    "dev-operator-b": {"name": "dev-operator-b", "tenant_id": "tenant-b", "role": "operator"},
    "dev-approver-b": {"name": "dev-approver-b", "tenant_id": "tenant-b", "role": "approver"},
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
    tenant_id = record.get("tenant_id", "")
    if role not in {"reader", "operator", "approver"} or not tenant_id:
        raise AuthError("token is missing a tenant or a role")
    return Principal(token_name=record.get("name", "unnamed"), tenant_id=tenant_id, role=role)
