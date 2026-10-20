"""Tenant-isolated run memory.

A key written for one tenant is invisible to every other tenant. The store
has no method that lists tenants together.
"""

from __future__ import annotations

import copy


class TenantMemory:
    def __init__(self) -> None:
        self._items: dict[str, dict[str, dict]] = {}

    def write(self, tenant: str, key: str, value: dict) -> None:
        if not tenant or not key:
            raise ValueError("tenant and key are required")
        self._items.setdefault(tenant, {})[key] = copy.deepcopy(value)

    def read(self, tenant: str, key: str) -> dict | None:
        row = self._items.get(tenant, {}).get(key)
        if row is None:
            return None
        return copy.deepcopy(row)
