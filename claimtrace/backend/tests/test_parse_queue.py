"""Background parsing, recovery, and deletion protection tests."""

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Event
from unittest.mock import Mock
from uuid import uuid4

import pytest
from backend.src.config import _load_settings
from backend.src.main import app
from backend.src.models import PaperRecord, PaperScope, ParsedDocument, ParseStatus
from backend.src.routes import parse as parse_route
from backend.src.services import pipeline_service
from backend.src.storage.paper_store import create_paper, get_paper
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def parse_executor(monkeypatch):
    pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="parse-test")
    monkeypatch.setattr(pipeline_service, "executor", pool)
    yield pool
    pool.shutdown(wait=True, cancel_futures=True)


def persist(storage_paths, paper_id, status, file_type="pdf", scope=PaperScope.LIBRARY):
    path = storage_paths["upload_dir"] / f"{paper_id}.{file_type}"
    path.write_bytes(b"%PDF-test")
    now = datetime.now(UTC)
    return create_paper(
        PaperRecord(
            paper_id=paper_id,
            original_filename=path.name,
            stored_filename=path.name,
            file_path=str(path),
            file_type=file_type,
            file_size=path.stat().st_size,
            status=status,
            scope=scope,
            created_at=now,
            updated_at=now,
        )
    )


@pytest.mark.parametrize("endpoint", ["/api/parse", "/api/verify/sources"])
def test_background_upload_returns_pending(client, monkeypatch, endpoint):
    monkeypatch.setattr(parse_route.settings, "parse_in_background", True)
    submit = Mock()
    monkeypatch.setattr(parse_route, "submit_parse", submit)
    response = client.post(endpoint, files={"file": ("paper.pdf", b"%PDF-test")})
    assert response.status_code == 200
    assert response.json()["status"] == "pending"
    submit.assert_called_once_with(response.json()["paper_id"])
    assert get_paper(response.json()["paper_id"]).status is ParseStatus.PENDING


def test_foreground_upload_completes(client, monkeypatch):
    monkeypatch.setattr(parse_route.settings, "parse_in_background", False)
    monkeypatch.setattr(
        pipeline_service,
        "parse_document",
        lambda paper_id, *args, **kwargs: ParsedDocument(paper_id=paper_id, pages=1),
    )
    response = client.post("/api/parse", files={"file": ("paper.pdf", b"%PDF-test")})
    assert response.status_code == 200
    assert response.json()["status"] == "completed"


def test_worker_failure_is_persisted(storage_paths, monkeypatch, parse_executor, caplog):
    paper_id = str(uuid4())
    persist(storage_paths, paper_id, ParseStatus.PENDING)

    def fail(*args, **kwargs):
        raise RuntimeError("unexpected parser failure")

    monkeypatch.setattr(pipeline_service, "parse_document", fail)
    with caplog.at_level(logging.ERROR):
        pipeline_service.submit_parse(paper_id)
        # A barrier in the same single worker runs after the parse wrapper.
        parse_executor.submit(lambda: None).result(timeout=5)
    record = get_paper(paper_id)
    assert record.status is ParseStatus.FAILED
    assert record.error_message
    assert "unexpected parser failure" in caplog.text


def test_recover_only_unfinished_pdfs(storage_paths):
    for status in ParseStatus:
        persist(storage_paths, status.value, status)
    persist(storage_paths, "bib", ParseStatus.PENDING, file_type="bib")
    persist(storage_paths, "source", ParseStatus.PROCESSING, scope=PaperScope.VERIFY_SOURCE)
    assert pipeline_service.recover_interrupted_parses() == 3
    for paper_id in ("pending", "processing", "source"):
        record = get_paper(paper_id)
        assert record.status is ParseStatus.FAILED
        assert record.error_message == (
            "Parsing was interrupted by a server restart. Please upload the file again."
        )
    assert get_paper("bib").status is ParseStatus.PENDING
    assert get_paper("completed").status is ParseStatus.COMPLETED
    assert get_paper("failed").error_message is None
    assert pipeline_service.recover_interrupted_parses() == 0


@pytest.mark.parametrize("status", [ParseStatus.PENDING, ParseStatus.PROCESSING])
def test_delete_unfinished_paper_conflicts(client, storage_paths, status):
    record = persist(storage_paths, "busy", status)
    response = client.delete("/api/papers/busy")
    assert response.status_code == 409
    assert response.json()["detail"] == (
        "The paper is still being parsed. Try again after parsing finishes."
    )
    assert get_paper("busy") == record
    assert (storage_paths["upload_dir"] / "busy.pdf").exists()


def test_queue_serializes_pdfs_and_keeps_api_responsive(client, monkeypatch):
    entered, release = Event(), Event()
    calls = []

    def parse(paper_id, *args, **kwargs):
        calls.append(paper_id)
        entered.set()
        assert release.wait(timeout=5)
        return ParsedDocument(paper_id=paper_id, pages=1)

    monkeypatch.setattr(parse_route.settings, "parse_in_background", True)
    monkeypatch.setattr(pipeline_service, "parse_document", parse)
    try:
        first = client.post("/api/parse", files={"file": ("first.pdf", b"%PDF-test")}).json()
        assert entered.wait(timeout=5)
        second = client.post("/api/parse", files={"file": ("second.pdf", b"%PDF-test")}).json()
        assert second["status"] == "pending"
        assert calls == [first["paper_id"]]
        assert client.get("/health").status_code == 200
        assert client.get("/api/papers").json()["total"] == 2
    finally:
        release.set()
    pipeline_service.executor.submit(lambda: None).result(timeout=5)
    assert calls == [first["paper_id"], second["paper_id"]]
    assert get_paper(first["paper_id"]).status is ParseStatus.COMPLETED
    assert get_paper(second["paper_id"]).status is ParseStatus.COMPLETED


def test_background_setting_defaults_true(monkeypatch):
    monkeypatch.delenv("PARSE_IN_BACKGROUND", raising=False)
    assert _load_settings().parse_in_background is True
    monkeypatch.setenv("PARSE_IN_BACKGROUND", "false")
    assert _load_settings().parse_in_background is False


def test_startup_recovers_and_status_exposes_reason(storage_paths, caplog):
    persist(storage_paths, "interrupted", ParseStatus.PROCESSING)
    with caplog.at_level(logging.WARNING), TestClient(app) as client:
        response = client.get("/api/parse/interrupted")
        assert response.status_code == 200
        assert response.json()["status"] == "failed"
        assert response.json()["error_message"] == (
            "Parsing was interrupted by a server restart. Please upload the file again."
        )
    assert "Recovered 1 interrupted PDF parses" in caplog.text
