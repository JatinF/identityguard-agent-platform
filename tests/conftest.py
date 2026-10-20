import pytest
from fastapi.testclient import TestClient

from identityguard.api.main import create_app
from identityguard.harness.recovery import open_service

ALEX_GOAL = (
    "Investigate the suspicious login for employee Alex Rivera, determine whether "
    "the account should be suspended, and request approval before taking action."
)


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def stack(tmp_path):
    service = open_service(tmp_path)
    client = TestClient(create_app(service))
    yield client, service
    service.close()
