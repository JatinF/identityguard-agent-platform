"""Model adapter contract.

Adapters return structured fields. They do not execute tools and they do not
decide approvals.
"""

from __future__ import annotations


class ModelTimeout(TimeoutError):
    pass


class ModelUnavailable(RuntimeError):
    pass


class ModelAdapter:
    name = "unset"

    def analyze(self, *, goal: str, evidence: list[dict], subject_id: str) -> dict:
        raise NotImplementedError
