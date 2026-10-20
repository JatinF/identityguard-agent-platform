"""Locate the repository datasets without assuming the install layout."""

from __future__ import annotations

import os
from pathlib import Path


def datasets_dir() -> Path:
    override = os.environ.get("IG_DATA_DIR")
    if override:
        return Path(override)
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "datasets" / "synthetic_identities.json"
        if candidate.is_file():
            return candidate.parent
    raise FileNotFoundError("datasets/synthetic_identities.json")
