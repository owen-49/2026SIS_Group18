"""API contract tests use an explicit fake external adapter, never live queries."""

import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from backend.src.audit_models import (
    BibliographicMetadata,
    ExternalRecord,
    LookupAttempt,
    LookupResult,
)
from backend.src.main import app
from backend.src.models import PaperRecord, ParsedDocument, ParseStatus
from backend.src.services import pipeline_service, reference_input_service
from backend.src.services.analysis_service import _find_bib_entry, _load_bibliography_entries
from backend.src.storage.paper_store import create_paper
from backend.src.storage.reference_store import ReferenceStoreError, reference_path
from engine.bib_parser import BibEntry
from pydantic import ValidationError

BIB = b"""@article{sample,
 title={Retrieval with citations}, author={Smith, Jane},
 year={2024}, journal={Journal of Retrieval}, doi={10.1234/example}
}"""


def upload_bib(client, content=BIB):
    response = client.post("/api/parse", files={"file": ("references.bib", content, "text/plain")})
    assert response.status_code == 200
    return response.json()["paper_id"]


def external_record(**changes):
    metadata = {
        "title": "Retrieval with citations",
        "authors": ["Smith, Jane"],
        "year": 2024,
        "venue": "Journal of Retrieval",
        "doi": "10.1234/example",
    }
    metadata.update(changes)
    return ExternalRecord(
        provider="test-registry",
        record_id="test-record",
        url="https://example.org/record",
        retrieved_at=datetime.now(UTC),
        metadata=BibliographicMetadata(**metadata),
    )


def lookup_result(outcome="found", records=None):
    if records is None:
        records = [external_record()] if outcome in ("found", "ambiguous") else []
    return LookupResult(
        outcome=outcome,
        records=records,
        attempts=[LookupAttempt(provider="test-registry", outcome=outcome)],
        reason="Test registry result",
    )


class FakeLookup:
    def __init__(self, result):
        self.result = result
        self.seen = []

    def lookup(self, entry):
        self.seen.append(entry)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def test_no_lookup_returns_explicit_failure_without_source_pdf_and_persists(client, monkeypatch):
    monkeypatch.delattr(app.state, "bibliography_lookup", raising=False)
    paper_id = upload_bib(client)
    response = client.post("/api/audit", json={"bib_paper_id": paper_id})
    assert response.status_code == 200
    body = response.json()
    assert body["contract_version"] == 2
    assert body["total_entries"] == 1
    assert body["status"] == "completed_with_errors"
    row = body["results"][0]
    assert row["status"] == "LOOKUP_FAILED"
    assert row["lookup_attempts"][0]["error_code"] == "EXTERNAL_LOOKUP_NOT_CONFIGURED"
    assert row["matched_record"] is None
    assert row["field_checks"] == []
    assert not {"claim", "verdict", "confidence", "source_passage"} & row.keys()
    assert not {"supported", "partial", "contradicted"} & body.keys()
    assert client.get(f"/api/audit/{body['audit_id']}").json() == body


@pytest.mark.parametrize(
    ("result", "expected"),
    [
        (lookup_result(), "VERIFIED"),
        (lookup_result(records=[external_record(year=2023)]), "METADATA_MISMATCH"),
        (lookup_result(records=[external_record(authors=[])]), "NEEDS_REVIEW"),
        (
            lookup_result("ambiguous", [external_record(), external_record(year=2023)]),
            "NEEDS_REVIEW",
        ),
        (lookup_result("not_found"), "NOT_FOUND"),
        (lookup_result("failed"), "LOOKUP_FAILED"),
        (TimeoutError("test timeout"), "LOOKUP_FAILED"),
    ],
)
def test_external_adapter_statuses_and_engine_field_comparison(
    client, monkeypatch, result, expected
):
    lookup = FakeLookup(result)
    monkeypatch.setattr(app.state, "bibliography_lookup", lookup, raising=False)
    response = client.post("/api/audit", json={"bib_paper_id": upload_bib(client)})
    assert response.status_code == 200
    body = response.json()
    assert sum(body["counts"].values()) == body["total_entries"] == 1
    row = body["results"][0]
    assert row["status"] == expected
    assert lookup.seen[0].metadata.title == "Retrieval with citations"
    if expected == "METADATA_MISMATCH":
        year = next(field for field in row["field_checks"] if field["field_name"] == "year")
        assert (year["input_value"], year["source_value"], year["status"]) == (
            "2024",
            "2023",
            "MISMATCH",
        )
        assert row["matched_record"]["url"] == "https://example.org/record"
    if expected == "NOT_FOUND":
        assert "does not prove fabrication" in row["reason"]


def test_fuzzy_engine_author_match_is_not_fully_verified(client, monkeypatch):
    lookup = FakeLookup(lookup_result(records=[external_record(authors=["Smith, John"])]))
    monkeypatch.setattr(app.state, "bibliography_lookup", lookup, raising=False)
    row = client.post("/api/audit", json={"bib_paper_id": upload_bib(client)}).json()["results"][0]
    assert row["status"] == "NEEDS_REVIEW"


def test_no_doi_is_sent_to_bibliographic_lookup(client, monkeypatch):
    lookup = FakeLookup(lookup_result(records=[external_record(doi="")]))
    monkeypatch.setattr(app.state, "bibliography_lookup", lookup, raising=False)
    paper_id = upload_bib(client, BIB.replace(b", doi={10.1234/example}", b""))
    row = client.post("/api/audit", json={"bib_paper_id": paper_id}).json()["results"][0]
    assert lookup.seen[0].metadata.doi == ""
    assert row["status"] == "VERIFIED"


def test_failed_entry_does_not_discard_other_entries(client, monkeypatch):
    class MixedLookup:
        def lookup(self, entry):
            if entry.metadata.key == "bad":
                raise TimeoutError()
            return lookup_result()

    monkeypatch.setattr(app.state, "bibliography_lookup", MixedLookup(), raising=False)
    content = BIB + BIB.replace(b"{sample,", b"{bad,")
    body = client.post("/api/audit", json={"bib_paper_id": upload_bib(client, content)}).json()
    assert [row["status"] for row in body["results"]] == ["VERIFIED", "LOOKUP_FAILED"]
    assert body["status"] == "completed_with_errors"


def persist_manuscript(storage_paths):
    path = storage_paths["upload_dir"] / "manuscript.pdf"
    path.write_bytes(b"Parser is substituted at its integration boundary in this test")
    timestamp = datetime.now(UTC)
    record = PaperRecord(
        paper_id=str(uuid4()),
        original_filename="manuscript.pdf",
        stored_filename=path.name,
        file_path=str(path),
        file_type="pdf",
        file_size=path.stat().st_size,
        status=ParseStatus.COMPLETED,
        created_at=timestamp,
        updated_at=timestamp,
    )
    create_paper(record)
    return record


def test_manuscript_reference_parser_preserves_raw_text_and_location(
    client, storage_paths, monkeypatch
):
    record = persist_manuscript(storage_paths)

    def extract(path):
        assert str(path) == record.file_path
        return SimpleNamespace(
            references=[
                SimpleNamespace(
                    raw_text="[7] Smith. Retrieval with citations. 2024.",
                    number=7,
                    page_start=4,
                    page_end=5,
                )
            ],
            warnings=["Parser sample warning"],
        )

    monkeypatch.setattr(reference_input_service, "extract_pdf_references", extract)
    lookup = FakeLookup(lookup_result())
    monkeypatch.setattr(app.state, "bibliography_lookup", lookup, raising=False)
    body = client.post("/api/audit", json={"manuscript_id": record.paper_id}).json()
    entry = body["results"][0]["entry"]
    assert (entry["number"], entry["page_start"], entry["page_end"]) == (7, 4, 5)
    assert entry["metadata"]["title"] == ""
    assert lookup.seen[0].metadata.raw_text.startswith("[7]")
    assert body["results"][0]["status"] == "NEEDS_REVIEW"
    assert "Parser sample warning" in body["warnings"]


def test_empty_reference_list_is_not_a_successful_audit(client, storage_paths, monkeypatch):
    record = persist_manuscript(storage_paths)
    monkeypatch.setattr(
        reference_input_service,
        "extract_pdf_references",
        lambda path: SimpleNamespace(references=[], warnings=[]),
    )
    body = client.post("/api/audit", json={"manuscript_id": record.paper_id}).json()
    assert body["status"] == "needs_review"
    assert body["total_entries"] == 0


def test_parser_dependency_error_is_explained(client, storage_paths, monkeypatch):
    record = persist_manuscript(storage_paths)

    def extract(path):
        raise reference_input_service.AuditInputError(
            503, "REFERENCE_PARSER_UNAVAILABLE", "Not installed"
        )

    monkeypatch.setattr(reference_input_service, "extract_pdf_references", extract)
    response = client.post("/api/audit", json={"manuscript_id": record.paper_id})
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "REFERENCE_PARSER_UNAVAILABLE"


@pytest.mark.parametrize("raw_entries", [[], [{"raw_text": "Smith (2024). Example."}]])
def test_reads_parser_public_reference_json_without_reextracting(
    client,
    storage_paths,
    monkeypatch,
    raw_entries,
):
    record = persist_manuscript(storage_paths)
    artifact = reference_path(record.paper_id)
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text(
        json.dumps(
            {
                "source_file": record.stored_filename,
                "references": raw_entries,
            }
        ),
        encoding="utf-8",
    )
    original = artifact.read_bytes()
    # A persisted result remains usable without the original PDF or Parser runtime.
    Path(record.file_path).unlink()

    def unexpected_extract(path):
        pytest.fail("Persisted Reference JSON must be reused")

    monkeypatch.setattr(reference_input_service, "extract_pdf_references", unexpected_extract)
    response = client.post("/api/audit", json={"manuscript_id": record.paper_id})
    assert response.status_code == 200
    assert response.json()["total_entries"] == len(raw_entries)
    assert artifact.read_bytes() == original
    if raw_entries:
        entry = response.json()["results"][0]["entry"]
        assert entry["metadata"]["raw_text"] == raw_entries[0]["raw_text"]
        assert entry["page_start"] is None
    else:
        assert response.json()["status"] == "needs_review"


def test_extracts_once_then_reuses_fields_and_warnings(client, storage_paths, monkeypatch):
    record = persist_manuscript(storage_paths)
    calls = []

    def extract(path):
        calls.append(path)
        return SimpleNamespace(
            references=[
                SimpleNamespace(
                    raw_text="[7] Smith (2024). Example.",
                    number=7,
                    page_start=3,
                    page_end=4,
                )
            ],
            warnings=["Check the reference boundary"],
        )

    monkeypatch.setattr(reference_input_service, "extract_pdf_references", extract)
    bodies = [
        client.post("/api/audit", json={"manuscript_id": record.paper_id}).json() for _ in range(2)
    ]
    assert len(calls) == 1
    assert bodies[0]["results"][0]["entry"] == bodies[1]["results"][0]["entry"]
    assert bodies[0]["warnings"] == bodies[1]["warnings"]
    assert bodies[1]["results"][0]["entry"]["page_end"] == 4
    saved = json.loads(reference_path(record.paper_id).read_text(encoding="utf-8"))
    assert saved["paper_id"] == record.paper_id
    assert len(saved["source_sha256"]) == 64

    Path(record.file_path).write_bytes(b"different manuscript")
    stale = client.post("/api/audit", json={"manuscript_id": record.paper_id})
    assert stale.status_code == 500
    assert stale.json()["detail"]["code"] == "REFERENCE_ARTIFACT_ERROR"
    assert len(calls) == 1


@pytest.mark.parametrize(
    "payload",
    [
        "{broken",
        "{}",
        '{"source_file":"manuscript.pdf","references":[{}]}',
        '{"source_file":"unrelated.pdf","references":[]}',
        '{"source_file":"manuscript.pdf","paper_id":"another-paper","references":[]}',
    ],
)
def test_bad_artifact_is_not_silently_replaced(client, storage_paths, monkeypatch, payload):
    record = persist_manuscript(storage_paths)
    artifact = reference_path(record.paper_id)
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text(payload, encoding="utf-8")

    def unexpected_extract(path):
        pytest.fail("A damaged artifact must not trigger a hidden re-extraction")

    monkeypatch.setattr(reference_input_service, "extract_pdf_references", unexpected_extract)
    response = client.post("/api/audit", json={"manuscript_id": record.paper_id})
    assert response.status_code == 500
    assert response.json()["detail"]["code"] == "REFERENCE_ARTIFACT_ERROR"
    assert artifact.read_text(encoding="utf-8") == payload


def test_reference_storage_failure_is_reported(client, storage_paths, monkeypatch):
    record = persist_manuscript(storage_paths)
    monkeypatch.setattr(
        reference_input_service,
        "extract_pdf_references",
        lambda path: SimpleNamespace(references=[], warnings=[]),
    )

    def fail_save(*args):
        raise ReferenceStoreError("Disk unavailable")

    monkeypatch.setattr(reference_input_service, "save_references", fail_save)
    response = client.post("/api/audit", json={"manuscript_id": record.paper_id})
    assert response.status_code == 500
    assert response.json()["detail"]["code"] == "REFERENCE_ARTIFACT_ERROR"


def test_explicit_pdf_reprocessing_invalidates_old_references(storage_paths, monkeypatch):
    record = persist_manuscript(storage_paths)
    artifact = reference_path(record.paper_id)
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text("old artifact", encoding="utf-8")

    def parse(paper_id, *args, **kwargs):
        assert not artifact.exists()
        return ParsedDocument(paper_id=paper_id, pages=1)

    monkeypatch.setattr(pipeline_service, "parse_document", parse)
    completed = pipeline_service.process_uploaded_paper(record.paper_id)
    assert completed.status == ParseStatus.COMPLETED
    assert not artifact.exists()


def test_legacy_source_ids_are_not_treated_as_existence_evidence(client):
    body = client.post(
        "/api/audit",
        json={
            "bib_paper_id": upload_bib(client),
            "source_paper_ids": ["nonexistent-pdf"],
        },
    ).json()
    assert body["results"][0]["status"] == "LOOKUP_FAILED"
    assert any("ignored" in warning for warning in body["warnings"])


@pytest.mark.parametrize(
    "body", [{}, {"bib_paper_id": "a", "manuscript_id": "b"}, {"bib_paper_id": " "}]
)
def test_audit_input_is_unambiguous(client, body):
    assert client.post("/api/audit", json=body).status_code == 422


def test_unknown_input_and_history(client):
    assert client.post("/api/audit", json={"bib_paper_id": "missing"}).status_code == 404
    assert client.get(f"/api/audit/{uuid4()}").status_code == 404
    assert client.get("/api/audit/invalid").status_code == 422


def test_failed_query_cannot_be_reported_as_not_found():
    with pytest.raises(ValidationError):
        LookupResult(
            outcome="not_found",
            reason="incorrect",
            attempts=[
                LookupAttempt(provider="test-registry", outcome="failed", error_code="TIMEOUT"),
            ],
        )


def test_claim_resolution_does_not_guess_numeric_order_or_duplicate_keys():
    entries = [BibEntry(key="one", title="First paper")]
    assert _find_bib_entry("[1]", entries) is None
    assert _find_bib_entry(r"\cite{one}", entries) is entries[0]
    assert _find_bib_entry(r"\cite{one}", entries + entries) is None
    assert _find_bib_entry(r"\cite{one,two}", entries) is None


def test_claims_do_not_combine_unrelated_bibliographies():
    records = [SimpleNamespace(file_type="bib", status=ParseStatus.COMPLETED) for _ in range(2)]
    assert _load_bibliography_entries(records) == []
