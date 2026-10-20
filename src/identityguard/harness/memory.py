"""Tenant memory helpers over the store."""

from __future__ import annotations


def remember(store, tenant_id: str, run_id: str, payload: dict) -> None:
    store.write_memory(tenant_id, f"run:{run_id}", payload)


def recall(store, tenant_id: str, run_id: str) -> dict | None:
    return store.read_memory(tenant_id, f"run:{run_id}")
