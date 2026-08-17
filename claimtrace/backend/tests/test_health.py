"""Health endpoint tests."""

from fastapi.testclient import TestClient

from src.main import app

client = TestClient(app)


def test_health_ok():
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["service"] == "claimtrace-api"
    assert body["version"] == "0.1.0"
