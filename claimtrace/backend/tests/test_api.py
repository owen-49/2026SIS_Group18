"""Frontend-facing API contract tests."""

import json
import uuid

from backend.src.routes import parse as parse_route


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


def test_audit_returns_consistent_non_empty_result(client):
    response = client.post(
        "/api/audit",
        json={
            "manuscript_id": "transformer-survey.pdf",
            "source_paper_ids": ["paper-attention", "paper-bert"],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total_citations"] == 2
    assert len(body["results"]) == 2
    assert (
        body["supported"]
        + body["partial"]
        + body["contradicted"]
        + body["not_found"]
        == body["total_citations"]
    )


def test_audit_rejects_empty_sources(client):
    response = client.post(
        "/api/audit",
        json={"manuscript_id": "manuscript.pdf", "source_paper_ids": []},
    )

    assert response.status_code == 400
