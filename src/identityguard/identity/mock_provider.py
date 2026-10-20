"""Load the synthetic directory and its events into a store."""

from __future__ import annotations

import json

from identityguard.paths import datasets_dir


def load_fixtures() -> tuple[list[dict], list[dict]]:
    root = datasets_dir()
    identities = json.loads((root / "synthetic_identities.json").read_text(encoding="utf-8"))
    events = json.loads((root / "security_events.json").read_text(encoding="utf-8"))
    if identities.get("real_accounts") != 0:
        raise ValueError("fixture file must declare real_accounts = 0")
    return list(identities["identities"]), list(events["events"])
