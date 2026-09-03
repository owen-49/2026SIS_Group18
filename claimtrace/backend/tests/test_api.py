"""Frontend-facing API contract tests."""

import json
import uuid
from datetime import UTC, datetime

from backend.src.models import PaperRecord, ParsedDocument, ParsedParagraph, ParseStatus
from backend.src.routes import parse as parse_route
from backend.src.storage.paper_store import create_paper, update_paper
from backend.src.storage.parsed_document_store import save_parsed_document


def _persist_parsed_pdf(storage_paths, paper_id: str, filename: str, document: ParsedDocument):
    """Create the same persisted records produced by the upload pipeline."""
    pdf_path = storage_paths["upload_dir"] / f"{paper_id}.pdf"
    pdf_path.write_bytes(b"persisted-test-pdf")
    timestamp = datetime.now(UTC)
    record = PaperRecord(
        paper_id=paper_id,
        original_filename=filename,
        stored_filename=pdf_path.name,
        file_path=str(pdf_path),
        file_type="pdf",
        file_size=pdf_path.stat().st_size,
        status=ParseStatus.COMPLETED,
        pages=document.pages,
        paragraph_count=len(document.paragraphs),
        title=document.title,
        created_at=timestamp,
        updated_at=timestamp,
    )
    create_paper(record)
    parsed_path = save_parsed_document(document)
    updated = update_paper(
        paper_id,
        {"parsed_result_path": str(parsed_path)},
    )
    assert updated is not None
    return updated


def test_health(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_frontend_cors_preflight(client):
    response = client.options(
        "/api/verify",
        headers={
            "Origin": "http://127.0.0.1:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:3000"


def test_extension_cors_preflight(client):
    extension_origin = f"chrome-extension://{'a' * 32}"
    response = client.options(
        "/api/papers",
        headers={
            "Origin": extension_origin,
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == extension_origin


def test_upload_pdf_persists_file_and_metadata(client, storage_paths, sample_pdf_bytes):
    content = sample_pdf_bytes
    response = client.post(
        "/api/parse",
        files={"file": ("paper.pdf", content, "application/pdf")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["file_type"] == "pdf"
    assert body["status"] == "completed"
    assert body["pages"] == 2
    assert body["paragraph_count"] >= 2
    assert body["title"] == "1 Introduction"
    assert body["paper_id"]

    uuid.UUID(body["paper_id"])
    stored_file = storage_paths["upload_dir"] / f"{body['paper_id']}.pdf"
    assert stored_file.read_bytes() == content

    papers_file = storage_paths["papers_file"]
    assert papers_file.exists()
    metadata = json.loads(papers_file.read_text(encoding="utf-8"))
    record = metadata["papers"][body["paper_id"]]
    assert record["original_filename"] == "paper.pdf"
    assert record["stored_filename"] == stored_file.name
    assert record["file_size"] == len(content)
    assert record["status"] == "completed"
    assert record["pages"] == 2
    assert record["paragraph_count"] == body["paragraph_count"]

    parsed_file = storage_paths["parsed_dir"] / f"{body['paper_id']}.json"
    parsed = json.loads(parsed_file.read_text(encoding="utf-8"))
    assert parsed["paper_id"] == body["paper_id"]
    assert len(parsed["paragraphs"]) == body["paragraph_count"]
    assert any("Self-attention" in paragraph["text"] for paragraph in parsed["paragraphs"])
    assert (storage_paths["parsed_dir"] / "markdown" / f"{body['paper_id']}.md").exists()
    assert record["parsed_result_path"] == str(parsed_file)


def test_uploaded_paper_can_be_read_from_json(client, sample_pdf_bytes):
    uploaded = client.post(
        "/api/parse",
        files={"file": ("paper.pdf", sample_pdf_bytes, "application/pdf")},
    ).json()

    response = client.get(f"/api/parse/{uploaded['paper_id']}")

    assert response.status_code == 200
    assert response.json() == uploaded


def test_list_papers_returns_empty_collection(client):
    response = client.get("/api/papers")

    assert response.status_code == 200
    assert response.json() == {"total": 0, "papers": []}


def test_list_papers_returns_newest_first_without_internal_paths(client, sample_pdf_bytes):
    first = client.post(
        "/api/parse",
        files={"file": ("first.pdf", sample_pdf_bytes, "application/pdf")},
    ).json()
    second = client.post(
        "/api/parse",
        files={"file": ("second.pdf", sample_pdf_bytes, "application/pdf")},
    ).json()

    response = client.get("/api/papers")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert [paper["paper_id"] for paper in body["papers"]] == [
        second["paper_id"],
        first["paper_id"],
    ]
    assert body["papers"][0]["original_filename"] == "second.pdf"
    assert body["papers"][0]["file_size"] == len(sample_pdf_bytes)
    assert body["papers"][0]["status"] == "completed"
    assert "created_at" in body["papers"][0]
    assert "file_path" not in body["papers"][0]
    assert "stored_filename" not in body["papers"][0]


def test_list_papers_returns_500_for_corrupt_metadata(client, storage_paths):
    storage_paths["papers_file"].write_text("{not valid json", encoding="utf-8")

    response = client.get("/api/papers")

    assert response.status_code == 500
    assert response.json()["detail"] == "Unable to read paper metadata."


def test_each_upload_gets_a_unique_paper_id(client, sample_pdf_bytes):
    first = client.post(
        "/api/parse",
        files={"file": ("first.pdf", sample_pdf_bytes, "application/pdf")},
    ).json()
    second = client.post(
        "/api/parse",
        files={"file": ("second.pdf", sample_pdf_bytes, "application/pdf")},
    ).json()

    assert first["paper_id"] != second["paper_id"]


def test_upload_bib(client):
    response = client.post(
        "/api/parse",
        files={"file": ("references.bib", b"@article{demo, title={Demo}}", "text/plain")},
    )

    assert response.status_code == 200
    assert response.json()["file_type"] == "bib"


def test_rejects_unsupported_file(client):
    response = client.post(
        "/api/parse",
        files={"file": ("notes.txt", b"notes", "text/plain")},
    )

    assert response.status_code == 415


def test_rejects_invalid_filename(client, storage_paths):
    response = client.post(
        "/api/parse",
        files={"file": ("../paper.pdf", b"%PDF-1.4\ntest", "application/pdf")},
    )

    assert response.status_code == 400
    assert not list(storage_paths["upload_dir"].glob("*.pdf"))
    assert not storage_paths["papers_file"].exists()


def test_rejects_empty_file(client, storage_paths):
    response = client.post(
        "/api/parse",
        files={"file": ("empty.pdf", b"", "application/pdf")},
    )

    assert response.status_code == 400
    assert not list(storage_paths["upload_dir"].glob("*.pdf"))
    assert not list(storage_paths["upload_dir"].rglob("*.part"))
    assert not storage_paths["papers_file"].exists()


def test_rejects_invalid_pdf_without_leaving_files(client, storage_paths):
    response = client.post(
        "/api/parse",
        files={"file": ("fake.pdf", b"not a PDF", "application/pdf")},
    )

    assert response.status_code == 415
    assert not list(storage_paths["upload_dir"].glob("*.pdf"))
    assert not list(storage_paths["upload_dir"].rglob("*.part"))
    assert not storage_paths["papers_file"].exists()


def test_rejects_oversized_file_without_leaving_files(
    client,
    storage_paths,
    monkeypatch,
):
    monkeypatch.setattr(parse_route, "MAX_UPLOAD_SIZE_BYTES", 8)

    response = client.post(
        "/api/parse",
        files={"file": ("large.pdf", b"%PDF-1.4 too large", "application/pdf")},
    )

    assert response.status_code == 413
    assert not list(storage_paths["upload_dir"].glob("*.pdf"))
    assert not list(storage_paths["upload_dir"].rglob("*.part"))
    assert not storage_paths["papers_file"].exists()


def test_unknown_paper_id_returns_404(client):
    response = client.get("/api/parse/does-not-exist")

    assert response.status_code == 404


def test_verify_returns_frontend_contract(client, sample_pdf_bytes):
    uploaded = client.post(
        "/api/parse",
        files={"file": ("attention.pdf", sample_pdf_bytes, "application/pdf")},
    ).json()

    response = client.post(
        "/api/verify",
        json={
            "claim": "Self-attention removes the need for recurrence.",
            "source_paper_id": uploaded["paper_id"],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["verdict"] == "SUPPORT"
    assert body["confidence"] > 0
    assert body["matches"]
    assert body["matches"][0]["passage_text"]


def test_verify_unknown_paper_returns_404(client):
    response = client.post(
        "/api/verify",
        json={
            "claim": "A claim with a missing source paper.",
            "source_paper_id": "does-not-exist",
        },
    )

    assert response.status_code == 404


def test_verify_rejects_empty_claim(client):
    response = client.post(
        "/api/verify",
        json={"claim": "   ", "source_paper_id": "paper-attention"},
    )

    assert response.status_code == 400


def test_claims_and_audit_use_persisted_parser_output(client, storage_paths):
    manuscript = _persist_parsed_pdf(
        storage_paths,
        "manuscript-1",
        "manuscript.pdf",
        ParsedDocument(
            paper_id="manuscript-1",
            title="Research Manuscript",
            pages=2,
            paragraphs=[
                ParsedParagraph(text="1 Introduction", page_start=1, page_end=1),
                ParsedParagraph(
                    text="Self-attention improves sequence modelling without recurrence [1].",
                    page_start=1,
                    page_end=1,
                ),
                ParsedParagraph(text="References", page_start=2, page_end=2),
                ParsedParagraph(
                    text="[1] Attention source article.",
                    page_start=2,
                    page_end=2,
                ),
            ],
        ),
    )
    source = _persist_parsed_pdf(
        storage_paths,
        "source-1",
        "attention-source.pdf",
        ParsedDocument(
            paper_id="source-1",
            title="Attention Source Article",
            authors=["Smith, Jane"],
            year=2024,
            pages=1,
            paragraphs=[
                ParsedParagraph(
                    text="Self-attention improves sequence modelling without recurrence.",
                    page_start=1,
                    page_end=1,
                )
            ],
        ),
    )

    claims_response = client.get(f"/api/papers/{manuscript.paper_id}/claims")
    assert claims_response.status_code == 200
    claims_body = claims_response.json()
    assert claims_body["status"] == "completed"
    assert len(claims_body["claims"]) == 1
    claim = claims_body["claims"][0]
    assert claim["text"] == "Self-attention improves sequence modelling without recurrence [1]."
    assert claim["citation_marker"] == "[1]"
    assert claim["manuscript_location"] == {"page": 1, "paragraph_index": 0}
    assert claims_body["manuscript_document"]["total_pages"] == 2

    response = client.post(
        "/api/audit",
        json={
            "manuscript_id": manuscript.paper_id,
            "source_paper_ids": [source.paper_id],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total_citations"] == 1
    assert len(body["results"]) == 1
    assert (
        body["supported"]
        + body["partial"]
        + body["contradicted"]
        + body["not_found"]
        == body["total_citations"]
    )
    result = body["results"][0]
    assert result["verdict"] == "SUPPORT"
    assert result["cited_source"]["source_paper_id"] == source.paper_id
    assert result["source_location"] == {
        "page": 1,
        "quote": "Self-attention improves sequence modelling without recurrence.",
        "annotation": "Matched source passage",
    }
    assert result["source_document"]["matched_location"] == {
        "page": 1,
        "paragraph_index": 0,
    }
    assert "Demo" not in result["comparison_rationale"]


def test_claims_unknown_paper_returns_404(client):
    response = client.get("/api/papers/does-not-exist/claims")

    assert response.status_code == 404


def test_claims_resolve_bib_key_to_matching_local_pdf(client, storage_paths):
    bib_response = client.post(
        "/api/parse",
        files={
            "file": (
                "references.bib",
                (
                    b"@article{attention2024, "
                    b"title={Attention Mechanisms in Deep Learning}, year={2024}}"
                ),
                "text/plain",
            )
        },
    )
    assert bib_response.status_code == 200

    source = _persist_parsed_pdf(
        storage_paths,
        "source-bib-1",
        "attention.pdf",
        ParsedDocument(
            paper_id="source-bib-1",
            title="Attention Mechanisms in Deep Learning",
            year=2024,
            pages=1,
            paragraphs=[
                ParsedParagraph(
                    text="Attention mechanisms connect information across positions.",
                    page_start=1,
                    page_end=1,
                )
            ],
        ),
    )
    manuscript = _persist_parsed_pdf(
        storage_paths,
        "manuscript-bib-1",
        "manuscript.pdf",
        ParsedDocument(
            paper_id="manuscript-bib-1",
            pages=1,
            paragraphs=[
                ParsedParagraph(
                    text=(
                        r"Attention mechanisms connect information across positions "
                        r"\cite{attention2024}."
                    ),
                    page_start=1,
                    page_end=1,
                )
            ],
        ),
    )

    response = client.get(f"/api/papers/{manuscript.paper_id}/claims")

    assert response.status_code == 200
    claim = response.json()["claims"][0]
    assert claim["resolution_status"] == "identified"
    assert claim["cited_source"]["source_paper_id"] == source.paper_id
    assert claim["cited_source"]["citation_key"] == "attention2024"
    assert claim["source_document"]["total_pages"] == 1


def test_audit_rejects_empty_sources(client):
    response = client.post(
        "/api/audit",
        json={"manuscript_id": "manuscript.pdf", "source_paper_ids": []},
    )

    assert response.status_code == 400
