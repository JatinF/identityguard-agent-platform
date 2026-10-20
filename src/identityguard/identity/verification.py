"""Independent reread after a tool reports success.

The tool result is not the account state. Completion is claimed only when the
reread matches the approved target state.
"""

from __future__ import annotations


def verify_account(identity: dict | None, expected_status: str, tool_result: dict | None) -> dict:
    reported_ok = bool(tool_result and tool_result.get("ok"))
    actual = None if identity is None else identity.get("status")
    if reported_ok and actual == expected_status:
        return {
            "status": "VERIFIED",
            "verification": "VERIFIED",
            "completed": True,
            "message": "Account state matches the approved action.",
        }
    return {
        "status": "UNVERIFIED",
        "verification": "UNVERIFIED",
        "completed": False,
        "message": "Tool result was not confirmed by a reread. The workflow stopped.",
    }
