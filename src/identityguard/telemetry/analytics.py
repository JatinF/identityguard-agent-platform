"""Analytics adapters.

ClickHouse and BigQuery are named slots for a later deployment. This demo
keeps evaluation counts in the process that ran the suite.
"""

from __future__ import annotations


class AnalyticsAdapter:
    name = "unconfigured"

    def export(self, rows: list[dict]) -> None:
        del rows
        raise RuntimeError("ClickHouse and BigQuery adapters are not wired")
