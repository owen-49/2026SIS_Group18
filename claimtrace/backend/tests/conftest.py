"""Shared backend API test fixtures."""

import pytest
from backend.src.main import app
from backend.src.routes import parse as parse_route
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """Use an isolated upload folder and in-memory paper store per test."""
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    monkeypatch.setattr(parse_route, "UPLOAD_DIR", upload_dir)
    parse_route._paper_store.clear()

    with TestClient(app) as test_client:
        yield test_client

    parse_route._paper_store.clear()
