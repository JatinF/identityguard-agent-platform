import json
import tempfile
import unittest
from pathlib import Path

from identityguard.acceptance_report import build_report, render_markdown, software_checks
from identityguard.asl import ASL_PATH, IAM_PATH, asl_problems, iam_problems, load_json
from identityguard.evals import render_eval, run_suite

ROOT = Path(__file__).resolve().parents[1]


class PlatformTests(unittest.TestCase):
    def test_state_machine_fail_closes(self) -> None:
        machine = load_json(ASL_PATH)
        self.assertEqual(asl_problems(machine), [])
        self.assertIn("has not been created in AWS", machine["Comment"])
        self.assertEqual(machine["States"]["Route"]["Default"], "Close")
        self.assertEqual(machine["States"]["RouteAfterApproval"]["Default"], "Close")

    def test_iam_is_limited_to_the_placeholder_account(self) -> None:
        document = load_json(IAM_PATH)
        self.assertEqual(iam_problems(document), [])

    def test_repo_ships_without_aws_evidence(self) -> None:
        self.assertFalse((ROOT / "benchmarks" / "aws-evidence.json").exists())

    def test_published_acceptance_is_no_go(self) -> None:
        self.assertTrue(software_checks())
        report = build_report(True)
        self.assertEqual(report["decision"], "NO-GO")
        text = (ROOT / "acceptance" / "deployment-acceptance.md").read_text(encoding="utf-8")
        self.assertEqual(text, render_markdown(report))

    def test_replay_report_matches_the_suite(self) -> None:
        results = run_suite()
        text = (ROOT / "evals" / "replay-report.md").read_text(encoding="utf-8")
        self.assertEqual(text, render_eval(results))
        self.assertNotIn("OVERRIDE-POLICY-TENANT-B", text)

    def test_measured_aws_evidence_can_flip_the_decision(self) -> None:
        records = [
            {
                "test_id": test_id,
                "evidence_class": "MEASURED",
                "result": "pass",
                "serials": ["arn:aws:states:us-east-1:000000000000:execution:identityguard:example"],
                "log": "execution-log.txt",
            }
            for test_id in ("stepfunctions-execution", "idp-provider-binding", "hosted-model-run")
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "aws-evidence.json"
            path.write_text(json.dumps({"records": records}), encoding="utf-8")
            report = build_report(True, path)
        self.assertEqual(report["decision"], "GO")


if __name__ == "__main__":
    unittest.main()
