"""Claim verification endpoint tests (mock mode, no LLM key)."""

from fastapi.testclient import TestClient

from src.main import app


def test_verify_returns_mock_verdict():
    # Use context manager so the startup event runs and app.state.llm_client is set.
    with TestClient(app) as client:
        resp = client.post(
            "/api/verify",
            json={"claim": "The method X improves accuracy", "source_paper_id": "abc123"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["claim"] == "The method X improves accuracy"
    assert body["verdict"] in {"SUPPORT", "PARTIAL", "CONTRADICT", "NOT_FOUND"}
    assert 0.0 <= body["confidence"] <= 1.0


def test_verify_rejects_empty_claim():
    with TestClient(app) as client:
        resp = client.post(
            "/api/verify",
            json={"claim": "   ", "source_paper_id": "abc123"},
        )
    assert resp.status_code == 400


def test_verify_rejects_missing_claim():
    with TestClient(app) as client:
        resp = client.post("/api/verify", json={"source_paper_id": "abc123"})
    assert resp.status_code == 422
