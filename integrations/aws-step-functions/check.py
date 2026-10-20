"""Static checks for the unexecuted Step Functions skeleton.

The checker does not call AWS. It rejects a definition that can execute a
write after a denial, a wildcard IAM statement, a foreign account id, or
embedded secret material.
"""

from __future__ import annotations

import json
import re


def check_definition(definition: dict, iam: dict) -> list[str]:
    errors: list[str] = []
    text = json.dumps({"definition": definition, "iam": iam})
    lowered = text.lower()
    if "akia" in lowered or "begin private" in lowered or "password" in lowered:
        errors.append("secret material")
    accounts = set(re.findall(r"(?<!\d)\d{12}(?!\d)", text))
    extra = accounts - {"000000000000"}
    if extra:
        errors.append("unexpected account " + ",".join(sorted(extra)))
    errors.extend(_iam_errors(iam))
    errors.extend(_asl_errors(definition))
    return errors


def _iam_errors(iam: dict) -> list[str]:
    errors = []
    for statement in iam.get("Statement", []):
        actions = statement.get("Action", [])
        resources = statement.get("Resource", [])
        if isinstance(actions, str):
            actions = [actions]
        if isinstance(resources, str):
            resources = [resources]
        for action in actions:
            if action == "*" or action.endswith(":*") or action.startswith("iam:") or action.startswith("secretsmanager:"):
                errors.append(f"iam action {action}")
        for resource in resources:
            if resource == "*":
                errors.append("iam resource star")
    return errors


def _asl_errors(definition: dict) -> list[str]:
    errors = []
    states = definition.get("States", {})
    if definition.get("StartAt") not in states:
        errors.append("start state missing")
    for name, state in states.items():
        if state.get("Type") == "Choice":
            if "Default" not in state:
                errors.append(f"{name} missing default")
            if state.get("Default") == "Execute":
                errors.append(f"{name} default executes")
            for choice in state.get("Choices", []):
                if choice.get("Next") == "Execute" and choice.get("StringEquals") != "ALLOW":
                    errors.append(f"{name} executes without ALLOW")
        if name == "WaitForApproval":
            if "TimeoutSeconds" not in state:
                errors.append("approval has no timeout")
            catches = state.get("Catch", [])
            if not catches:
                errors.append("approval has no catch")
            for catch in catches:
                if catch.get("Next") != "Close":
                    errors.append("approval failure does not close")
    return errors
