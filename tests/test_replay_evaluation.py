"""Replay, release gate, and the committed benchmark page."""

import importlib.util
import json
from pathlib import Path

import pytest

from identityguard.evaluations.metrics import render_benchmark_report
from identityguard.evaluations.regression import release_gate
from identityguard.evaluations.runner import load_jsonl, replay_trace, run_suite
from identityguard.harness.recovery import open_service
from identityguard.models.base import ModelTimeout, ModelUnavailable
from identityguard.models.bedrock_adapter import BedrockAdapter
from identityguard.models.hosted import AnthropicAdapter, XAIAdapter
from identityguard.models.mock_adapter import BlindModel, MockModel, TimeoutModel
from identityguard.models.openai_adapter import OpenAIAdapter
from identityguard.principals import authenticate
from identityguard.telemetry.analytics import AnalyticsAdapter
from tests.conftest import ALEX_GOAL, bearer

ROOT = Path(__file__).resolve().parents[1]


def test_golden_cases_match_without_a_hosted_model():
    from identityguard.evaluations.runner import execute_case

    for case in load_jsonl("golden_evaluations.jsonl"):
        outcome = execute_case(case, MockModel())
        assert outcome["status"] == case["expect_status"]
        if case["expect_active"]:
            assert outcome["account_status"] in {None, "active"}
        assert outcome["effects"] == 0
        assert outcome["completion_claimed"] is False


def test_release_gate_blocks_a_worse_model():
    baseline = run_suite(MockModel(), approve_alex=True)
    candidate = run_suite(BlindModel(), approve_alex=True)
    gate = release_gate(baseline, candidate)
    assert baseline["missed_risks"] == 0
    assert baseline["verified_completions"] == 1
    assert baseline["unauthorized_writes"] == 0
    assert baseline["injection_blocked"] == 3
    assert candidate["missed_risks"] > baseline["missed_risks"]
    assert gate["model_release"] == "BLOCK"
    assert gate["deployment_decision"] == "NO-GO"
    assert release_gate(baseline, baseline)["model_release"] == "ALLOW"


def test_replay_of_a_failed_trace_still_rejects_invented_evidence():
    result = replay_trace(
        {
            "id": "invented-evidence",
            "token": "dev-operator-a",
            "subject_id": "SYN-USER-ALEX",
            "goal": ALEX_GOAL,
            "model": "inventing",
            "expect_status": "EVIDENCE_REJECTED",
        }
    )
    assert result["matched"] is True
    assert result["effects"] == 0
    assert result["completed"] is False


def test_model_timeout_retries_then_fails_closed(tmp_path):
    recovered = open_service(tmp_path / "retry", model=TimeoutModel(failures=2))
    try:
        operator = authenticate("Bearer dev-operator-a")
        view = recovered.start(operator, subject_id="SYN-USER-ALEX", goal=ALEX_GOAL, idempotency_key="retry-1")
        assert view["status"] == "AWAITING_APPROVAL"
        assert recovered.store.count_effects("SYN-USER-ALEX") == 0
        assert recovered.store.get_identity("tenant-a", "SYN-USER-ALEX")["status"] == "active"
    finally:
        recovered.close()
    failed = open_service(tmp_path / "fail", model=TimeoutModel(failures=5))
    try:
        operator = authenticate("Bearer dev-operator-a")
        view = failed.start(operator, subject_id="SYN-USER-ALEX", goal=ALEX_GOAL, idempotency_key="fail-1")
        assert view["status"] == "FAILED"
        assert view["completion_claimed"] is False
        assert "success" not in view["message"].lower()
        assert failed.store.count_effects("SYN-USER-ALEX") == 0
    finally:
        failed.close()


def test_hosted_adapters_do_not_call_the_network(monkeypatch):
    monkeypatch.setenv("XAI_API_KEY", "fixture-key")

    def transport(url, payload, key):
        assert url == "https://api.x.ai/v1/chat/completions"
        assert payload["model"] == "grok-4.7"
        assert payload["stream"] is False
        assert key == "fixture-key"
        raise TimeoutError("timed out")

    with pytest.raises(ModelTimeout):
        XAIAdapter(transport=transport).analyze(goal="g", evidence=[], subject_id="SYN-USER-ALEX")

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ModelUnavailable):
        OpenAIAdapter().analyze(goal="g", evidence=[], subject_id="SYN-USER-ALEX")

    monkeypatch.setenv("ANTHROPIC_API_KEY", "fixture-key")

    def anthropic_transport(url, payload, key):
        assert url == "https://api.anthropic.com/v1/messages"
        raise TimeoutError("timed out")

    with pytest.raises(ModelTimeout):
        AnthropicAdapter(transport=anthropic_transport).analyze(goal="g", evidence=[], subject_id="SYN-USER-ALEX")

    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "EXAMPLEKEY")
    with pytest.raises(ModelUnavailable, match="not enabled"):
        BedrockAdapter().analyze(goal="g", evidence=[], subject_id="SYN-USER-ALEX")


def test_evaluation_report_and_benchmark_page(stack):
    client, _service = stack
    denied = client.get("/v1/evaluations/report")
    assert denied.status_code == 401
    report = client.get("/v1/evaluations/report", headers=bearer("dev-reader-a")).json()
    assert report["deployment_decision"] == "NO-GO"
    assert report["baseline"]["release_gate"] == "ALLOW"
    assert report["candidate"]["release_gate"] == "BLOCK"
    assert report["latency"]["evidence_class"] == "EXAMPLE"
    assert report["latency"]["scope"] == "local-replay"
    assert report["latency"]["p95_ms"] >= 0
    assert report["cost"]["evidence_class"] == "ASSUMPTION"
    assert report["external_gates"]["hosted-model-run"] == "not-run"
    assert report["replay"]["matched"] is True
    assert report["unverified"]["status"] == "UNVERIFIED"
    assert report["unverified"]["completed"] is False
    assert report["retries"]["recovered_status"] == "AWAITING_APPROVAL"
    assert report["retries"]["exhausted_status"] == "FAILED"
    text = (ROOT / "benchmarks" / "benchmark_report.md").read_text(encoding="utf-8")
    assert text == render_benchmark_report()
    assert "MEASURED |" not in text or "Absent" in text
    assert not (ROOT / "benchmarks" / "aws-evidence.json").exists()


def test_step_functions_skeleton_and_local_adapters():
    checker_path = ROOT / "integrations" / "aws-step-functions" / "check.py"
    spec = importlib.util.spec_from_file_location("asl_check", checker_path)
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    check_definition = checker.check_definition

    definition = json.loads((ROOT / "integrations" / "aws-step-functions" / "definition.asl.json").read_text(encoding="utf-8"))
    iam = json.loads((ROOT / "integrations" / "aws-step-functions" / "iam-tool-role.json").read_text(encoding="utf-8"))
    assert check_definition(definition, iam) == []
    broken = json.loads(json.dumps(definition))
    broken["States"]["Reauthorize"]["Default"] = "Execute"
    assert check_definition(broken, iam)
    dashboard = json.loads((ROOT / "dashboards" / "grafana" / "identityguard.json").read_text(encoding="utf-8"))
    assert "identityguard_runs_total" in json.dumps(dashboard)
    with pytest.raises(RuntimeError, match="not wired"):
        AnalyticsAdapter().export([])
