"""Verify-only source PDF upload boundaries."""

from pathlib import Path

from backend.src.storage.paper_store import get_paper


def test_verify_source_upload_has_separate_storage_and_listing(
    client, sample_pdf_bytes, storage_paths
):
    response = client.post(
        "/api/verify/sources",
        files={"file": ("source.pdf", sample_pdf_bytes, "application/pdf")},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["scope"] == "verify_source"

    record = get_paper(body["paper_id"])
    assert record is not None
    assert Path(record.file_path).parent == storage_paths["upload_dir"] / "verify-sources"
    assert Path(record.parsed_result_path).parent == storage_paths["parsed_dir"] / "verify-sources"

    assert client.get("/api/papers").json() == {"total": 0, "papers": []}
    listed = client.get("/api/verify/sources")
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["papers"][0]["paper_id"] == body["paper_id"]
    assert listed.json()["papers"][0]["scope"] == "verify_source"


def test_verify_source_cannot_be_used_as_manuscript_audit_or_legacy_verify(
    client, sample_pdf_bytes
):
    uploaded = client.post(
        "/api/verify/sources",
        files={"file": ("source.pdf", sample_pdf_bytes, "application/pdf")},
    ).json()
    paper_id = uploaded["paper_id"]

    legacy_verify = client.post(
        "/api/verify",
        json={"claim": "A claim.", "source_paper_id": paper_id},
    )
    assert legacy_verify.status_code == 422

    claims = client.get(f"/api/papers/{paper_id}/claims")
    assert claims.status_code == 422

    audit = client.post("/api/audit", json={"manuscript_id": paper_id})
    assert audit.status_code == 422
    assert audit.json()["detail"]["code"] == "INPUT_SCOPE_MISMATCH"


def test_bib_verification_does_not_use_verify_only_sources(client, sample_pdf_bytes):
    bib = client.post(
        "/api/parse",
        files={"file": ("references.bib", b"@article{source, title={Source}}", "text/plain")},
    ).json()
    source = client.post(
        "/api/verify/sources",
        files={"file": ("source.pdf", sample_pdf_bytes, "application/pdf")},
    ).json()

    response = client.post(
        "/api/verify/bib",
        json={"bib_paper_id": bib["paper_id"], "source_paper_ids": [source["paper_id"]]},
    )

    assert response.status_code == 200
    assert response.json()["results"][0]["fields"][0]["status"] == "PDF_MISSING"
