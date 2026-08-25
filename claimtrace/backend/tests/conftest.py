"""Shared backend API test fixtures."""

import pytest
from backend.src.main import app
from backend.src.routes import parse as parse_route
from backend.src.storage import paper_store, parsed_document_store
from fastapi.testclient import TestClient


@pytest.fixture()
def storage_paths(tmp_path, monkeypatch):
    """Point file and JSON persistence at an isolated test directory."""
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    papers_file = upload_dir / "papers.json"
    parsed_dir = tmp_path / "parsed"

    monkeypatch.setattr(parse_route, "UPLOAD_DIR", upload_dir)
    monkeypatch.setattr(paper_store, "PAPERS_FILE", papers_file)
    monkeypatch.setattr(parsed_document_store, "PARSED_DIR", parsed_dir)

    return {
        "upload_dir": upload_dir,
        "papers_file": papers_file,
        "parsed_dir": parsed_dir,
    }


@pytest.fixture()
def client(storage_paths):
    """Return an API client using isolated local persistence."""
    del storage_paths

    with TestClient(app) as test_client:
        yield test_client
