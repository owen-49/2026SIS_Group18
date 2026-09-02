"""Shared backend API test fixtures."""

import fitz
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
def sample_pdf_bytes():
    """Return a valid two-page PDF for Parser-backed API tests."""
    document = fitz.open()
    first_page = document.new_page()
    first_page.insert_text((72, 72), "1 Introduction", fontsize=20)
    first_page.insert_text(
        (72, 115),
        "Self-attention enables the model to relate information from different positions "
        "without recurrence.",
        fontsize=11,
    )
    second_page = document.new_page()
    second_page.insert_text((72, 72), "2 Methods", fontsize=20)
    second_page.insert_text(
        (72, 115),
        "The experiment evaluates citation verification quality using source passages.",
        fontsize=11,
    )
    pdf_bytes = document.tobytes()
    document.close()
    return pdf_bytes


@pytest.fixture()
def client(storage_paths):
    """Return an API client using isolated local persistence."""
    del storage_paths

    with TestClient(app) as test_client:
        yield test_client
