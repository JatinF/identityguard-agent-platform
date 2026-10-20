"""Prometheus collectors on a private registry."""

from __future__ import annotations

from prometheus_client import CollectorRegistry, Counter, generate_latest


def build_metrics() -> tuple[CollectorRegistry, Counter, Counter]:
    registry = CollectorRegistry()
    runs = Counter(
        "identityguard_runs_total",
        "Investigation views recorded by this process.",
        ["status"],
        registry=registry,
    )
    approvals = Counter(
        "identityguard_approval_decisions_total",
        "Approval decisions accepted by this process.",
        ["decision"],
        registry=registry,
    )
    return registry, runs, approvals


def render_metrics(registry: CollectorRegistry) -> bytes:
    return generate_latest(registry)
