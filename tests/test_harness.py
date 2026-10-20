import tempfile
import unittest
from pathlib import Path

from langgraph.types import Command

from identityguard.auth import authenticate
from identityguard.evals import isolation_check, recovery_check, run_suite
from identityguard.harness import HarnessError, open_harness


class HarnessTests(unittest.TestCase):
    def test_golden_cases_pass(self) -> None:
        results = run_suite()
        failed = [item for item in results if not item["passed"]]
        self.assertEqual(failed, [])

    def test_suite_is_replayable(self) -> None:
        first = [(item["id"], item["passed"], item["status"]) for item in run_suite()]
        second = [(item["id"], item["passed"], item["status"]) for item in run_suite()]
        self.assertEqual(first, second)

    def test_checkpoint_survives_a_reopened_database(self) -> None:
        self.assertTrue(recovery_check())

    def test_memory_and_export_stay_inside_the_tenant(self) -> None:
        self.assertTrue(isolation_check())

    def test_forged_self_approval_does_not_disable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            harness = open_harness(root / "runs.sqlite", root / "audit.jsonl")
            try:
                request_id = "SYN-REQ-301"
                harness.start(
                    authenticate("Bearer dev-approver-a"),
                    {"request_id": request_id, "operation": "disable-account", "target": "SYN-USER-014"},
                )
                harness.graph.invoke(
                    Command(
                        resume={
                            "approval_id": "APR-301",
                            "approver": "dev-approver-a",
                            "approver_role": "approver",
                            "tenant": "tenant-a",
                            "request_id": request_id,
                        }
                    ),
                    {"configurable": {"thread_id": request_id}},
                )
                view = harness.view(request_id)
                self.assertEqual(view["status"], "denied")
                self.assertEqual(view["target_status"], "active")
                self.assertFalse(view["mutated"])
            finally:
                harness.close()

    def test_tool_outage_fail_closes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            harness = open_harness(root / "runs.sqlite", root / "audit.jsonl", force_tool_down=True)
            try:
                request_id = "SYN-REQ-302"
                harness.start(
                    authenticate("Bearer dev-operator-a"),
                    {"request_id": request_id, "operation": "disable-account", "target": "SYN-USER-014"},
                )
                done = harness.resume(authenticate("Bearer dev-approver-a"), request_id, "APR-302")
                self.assertEqual(done["status"], "failed")
                self.assertFalse(done["verified"])
                self.assertFalse(done["mutated"])
                self.assertEqual(done["target_status"], "active")
            finally:
                harness.close()

    def test_duplicate_start_is_a_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            harness = open_harness(root / "runs.sqlite", root / "audit.jsonl")
            try:
                request = {"request_id": "SYN-REQ-303", "operation": "lookup-account", "target": "SYN-USER-001"}
                who = authenticate("Bearer dev-reader-a")
                harness.start(who, request)
                with self.assertRaises(HarnessError) as caught:
                    harness.start(who, request)
                self.assertEqual(caught.exception.status_code, 409)
            finally:
                harness.close()


if __name__ == "__main__":
    unittest.main()
