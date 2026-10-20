import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from identityguard.api import create_app


class ApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.audit = root / "audit.jsonl"
        self.client = TestClient(create_app(self.audit, root / "runs.sqlite"))

    def tearDown(self) -> None:
        self.client.app.state.harness.close()
        self.tmp.cleanup()

    def test_missing_token_is_unauthorized(self) -> None:
        response = self.client.post(
            "/v1/runs",
            json={"request_id": "SYN-REQ-400", "operation": "lookup-account", "target": "SYN-USER-001"},
        )
        self.assertEqual(response.status_code, 401)
        self.assertNotIn("SYN-USER-001", self.audit.read_text(encoding="utf-8"))

    def test_body_tenant_cannot_cross_tenants(self) -> None:
        response = self.client.post(
            "/v1/runs",
            headers={"Authorization": "Bearer dev-operator-a"},
            json={
                "request_id": "SYN-REQ-401",
                "operation": "disable-account",
                "target": "SYN-USER-200",
                "tenant": "tenant-b",
                "justification": "switch tenant",
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["tenant"], "tenant-a")
        self.assertEqual(body["status"], "denied")
        other = self.client.get("/v1/runs/SYN-REQ-401", headers={"Authorization": "Bearer dev-operator-b"})
        self.assertEqual(other.status_code, 404)

    def test_credential_material_is_dropped(self) -> None:
        response = self.client.post(
            "/v1/runs",
            headers={"Authorization": "Bearer dev-reader-a"},
            json={
                "request_id": "SYN-REQ-402",
                "operation": "lookup-account",
                "target": "SYN-USER-001",
                "password": "hunter2",
            },
        )
        self.assertEqual(response.status_code, 422)
        text = response.text + self.audit.read_text(encoding="utf-8")
        self.assertNotIn("hunter2", text)

    def test_resume_requires_a_different_approver(self) -> None:
        headers = {"Authorization": "Bearer dev-operator-a"}
        started = self.client.post(
            "/v1/runs",
            headers=headers,
            json={"request_id": "SYN-REQ-403", "operation": "disable-account", "target": "SYN-USER-014"},
        )
        self.assertEqual(started.status_code, 200)
        self.assertEqual(started.json()["status"], "awaiting-approval")
        reader = self.client.post(
            "/v1/runs/SYN-REQ-403/resume",
            headers={"Authorization": "Bearer dev-reader-a"},
            json={"approval_id": "APR-403"},
        )
        self.assertEqual(reader.status_code, 403)
        other_tenant = self.client.post(
            "/v1/runs/SYN-REQ-403/resume",
            headers={"Authorization": "Bearer dev-approver-b"},
            json={"approval_id": "APR-403"},
        )
        self.assertEqual(other_tenant.status_code, 404)
        approved = self.client.post(
            "/v1/runs/SYN-REQ-403/resume",
            headers={"Authorization": "Bearer dev-approver-a"},
            json={"approval_id": "APR-403", "approver": "dev-operator-a"},
        )
        self.assertEqual(approved.status_code, 200)
        self.assertEqual(approved.json()["target_status"], "disabled")
        self.assertNotIn("switch tenant", self.audit.read_text(encoding="utf-8").lower())

    def test_metrics_are_local_counters(self) -> None:
        self.client.post(
            "/v1/runs",
            headers={"Authorization": "Bearer dev-reader-a"},
            json={"request_id": "SYN-REQ-404", "operation": "delete-tenant", "target": "SYN-USER-001"},
        )
        text = self.client.get("/metrics").text
        self.assertIn("identityguard_runs_total 1", text)
        self.assertIn("identityguard_runs_denied_total 1", text)
        self.assertIn("Not cloud telemetry", text)


if __name__ == "__main__":
    unittest.main()
