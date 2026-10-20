"""Checks for the Step Functions definition.

The checker walks the Amazon States Language document. It does not call AWS.
A choice without a default, or a deny path that reaches Execute, is a failure.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ASL_PATH = ROOT / "deploy" / "stepfunctions" / "identity-workflow.asl.json"
IAM_PATH = ROOT / "deploy" / "iam" / "tool-role.json"
ACCOUNT = "000000000000"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def asl_problems(machine: dict) -> list[str]:
    problems: list[str] = []
    states = machine.get("States")
    if not isinstance(states, dict) or not states:
        return ["States is missing"]
    start = machine.get("StartAt")
    if start not in states:
        problems.append("StartAt does not name a state")
    for name, state in states.items():
        if not isinstance(state, dict):
            problems.append(f"{name} is not an object")
            continue
        kind = state.get("Type")
        if kind not in {"Pass", "Task", "Choice"}:
            problems.append(f"{name} has unsupported type")
        if kind == "Choice":
            if "Default" not in state:
                problems.append(f"{name} has no default")
            for choice in state.get("Choices", []):
                _exists(states, choice.get("Next"), problems, name)
                if choice.get("StringEquals") == "deny" and choice.get("Next") == "Execute":
                    problems.append(f"{name} sends deny to Execute")
                if choice.get("Next") == "Execute" and choice.get("StringEquals") != "allow":
                    problems.append(f"{name} reaches Execute without an allow choice")
            _exists(states, state.get("Default"), problems, name)
        else:
            if state.get("End") is True and "Next" in state:
                problems.append(f"{name} both ends and continues")
            if state.get("End") is not True:
                _exists(states, state.get("Next"), problems, name)
        for catch in state.get("Catch", []):
            _exists(states, catch.get("Next"), problems, name)
            if catch.get("Next") == "Execute":
                problems.append(f"{name} catch continues to Execute")
    if "Execute" in states and _reachable(states, start, "Execute"):
        pass
    waiting = states.get("WaitForApproval", {})
    if waiting.get("Next") == "Execute":
        problems.append("WaitForApproval continues directly to Execute")
    problems.extend(_account_problems(json.dumps(machine)))
    return problems


def iam_problems(document: dict) -> list[str]:
    problems: list[str] = []
    statements = document.get("Statement")
    if not isinstance(statements, list) or not statements:
        return ["Statement is missing"]
    for index, statement in enumerate(statements):
        actions = statement.get("Action", [])
        if isinstance(actions, str):
            actions = [actions]
        resources = statement.get("Resource", [])
        if isinstance(resources, str):
            resources = [resources]
        if statement.get("Effect") != "Allow":
            problems.append(f"statement {index} is not an allow")
        if "*" in actions or any(action == "*" or action.endswith(":*") for action in actions):
            problems.append(f"statement {index} uses a wildcard action")
        if "*" in resources:
            problems.append(f"statement {index} uses a wildcard resource")
        for action in actions:
            if action.startswith("iam:") or action.startswith("secretsmanager:"):
                problems.append(f"statement {index} grants {action}")
    problems.extend(_account_problems(json.dumps(document)))
    return problems


def _exists(states: dict, name: str | None, problems: list[str], owner: str) -> None:
    if not name or name not in states:
        problems.append(f"{owner} points at missing state {name}")


def _reachable(states: dict, start: str | None, goal: str) -> bool:
    seen: set[str] = set()
    stack = [start] if start else []
    while stack:
        current = stack.pop()
        if not current or current in seen or current not in states:
            continue
        seen.add(current)
        state = states[current]
        nxt = []
        if state.get("Next"):
            nxt.append(state["Next"])
        if state.get("Default"):
            nxt.append(state["Default"])
        for choice in state.get("Choices", []):
            nxt.append(choice.get("Next"))
        for catch in state.get("Catch", []):
            nxt.append(catch.get("Next"))
        stack.extend(nxt)
    return goal in seen


def _account_problems(blob: str) -> list[str]:
    problems = []
    if "AKIA" in blob or "password" in blob.lower() or "BEGIN PRIVATE" in blob:
        problems.append("document contains credential material")
    for account in re.findall(r"\d{12}", blob):
        if account != ACCOUNT:
            problems.append(f"unexpected account id {account}")
    return problems
