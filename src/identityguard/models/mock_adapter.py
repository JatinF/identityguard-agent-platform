"""Deterministic investigator.

Suspicious-login evidence for the subject produces a suspend proposal and
cites only those evidence ids. Jailbreak text can set skip_approval. The
harness is required to ignore that flag.
"""

from __future__ import annotations

from identityguard.models.base import ModelAdapter

INJECTION_MARKERS = ("bypass approval", "ignore approval", "skip the approver", "policy disabled")


class MockModel(ModelAdapter):
    name = "mock"

    def analyze(self, *, goal: str, evidence: list[dict], subject_id: str) -> dict:
        cited = [
            row["evidence_id"]
            for row in evidence
            if row.get("subject_id") == subject_id and row.get("kind") == "suspicious-login"
        ]
        lowered = goal.lower() + " " + " ".join(str(row.get("body", "")) for row in evidence).lower()
        action = None
        if cited:
            action = {
                "tool": "suspend-account",
                "arguments": {"identity_id": subject_id, "reason": "suspicious-login"},
            }
        return {
            "risk": "high" if cited else "none",
            "evidence_ids": cited,
            "recommended_action": action,
            "skip_approval": any(marker in lowered for marker in INJECTION_MARKERS),
            "tokens": 120,
            "model": self.name,
        }


class InventingModel(ModelAdapter):
    """Cites an evidence id that was never retrieved."""

    name = "inventing"

    def analyze(self, *, goal: str, evidence: list[dict], subject_id: str) -> dict:
        return {
            "risk": "high",
            "evidence_ids": ["SYN-EV-DOES-NOT-EXIST"],
            "recommended_action": {
                "tool": "suspend-account",
                "arguments": {"identity_id": subject_id, "reason": "unlisted-evidence"},
            },
            "skip_approval": False,
            "tokens": 80,
            "model": self.name,
        }


class TimeoutModel(ModelAdapter):
    name = "timeout"

    def __init__(self, failures: int = 3):
        self.failures = failures
        self.calls = 0

    def analyze(self, *, goal: str, evidence: list[dict], subject_id: str) -> dict:
        from identityguard.models.base import ModelTimeout

        self.calls += 1
        if self.calls <= self.failures:
            raise ModelTimeout("model timed out")
        return MockModel().analyze(goal=goal, evidence=evidence, subject_id=subject_id)


class BlindModel(ModelAdapter):
    """Drops a real suspicious-login finding. Used to score missed risk."""

    name = "blind"

    def analyze(self, *, goal: str, evidence: list[dict], subject_id: str) -> dict:
        return {
            "risk": "none",
            "evidence_ids": [],
            "recommended_action": None,
            "skip_approval": False,
            "tokens": 40,
            "model": self.name,
        }
