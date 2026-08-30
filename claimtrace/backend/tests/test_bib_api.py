"""BibTeX upload, persistence, and verification API tests."""

import json
from pathlib import Path

from backend.src.storage.bib_document_store import load_bib_document
from backend.tests.pdf_fixtures import make_test_pdf

SAMPLE_BIB = b"""
@article{attention2024,
  title={Attention Mechanisms in Deep Learning},
  author={Smith, John and Doe, Jane},
  year={2024},
  journal={Journal of Machine Learning Research}
}
@inproceedings{retrieval2023,
  title={Reliable Retrieval for Citation Verification},
  author={Chen, Hong and Sun, Siyuan},
  year={2023},
  booktitle={Proceedings of the Example Conference}
}
@misc{metadata2022,
  title={Practical Metadata Checking},
  author={Lee, Alex},
  year={2022}
}
"""


def _upload_bib(client):
    return client.post(
        "/api/parse",
        files={"file": ("references.bib", SAMPLE_BIB, "text/plain")},
    )


def test_upload_bib_parses_and_persists_three_entries(client, storage_paths):
    response = _upload_bib(client)

    assert response.status_code == 200
    body = response.json()
    assert body["file_type"] == "bib"
    assert body["status"] == "completed"
    assert body["entry_count"] == 3

    metadata = json.loads(storage_paths["papers_file"].read_text(encoding="utf-8"))
    record = metadata["papers"][body["paper_id"]]
    parsed_path = Path(record["parsed_result_path"])
    assert parsed_path.parent == storage_paths["bib_parsed_dir"]

    document = load_bib_document(parsed_path)
    assert document.paper_id == body["paper_id"]
    assert [entry.key for entry in document.entries] == [
        "attention2024",
        "retrieval2023",
        "metadata2022",
    ]


def test_parse_bib_compatibility_endpoint_reuses_real_parser(client):
    uploaded = _upload_bib(client).json()

    response = client.post(
        "/api/parse/bib",
        json={"paper_id": uploaded["paper_id"]},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    assert response.json()["entry_count"] == 3


def test_uploaded_bib_status_can_be_read(client):
    uploaded = _upload_bib(client).json()

    response = client.get(f"/api/parse/{uploaded['paper_id']}")

    assert response.status_code == 200
    assert response.json() == uploaded


def test_upload_without_bib_entries_returns_422_and_records_failure(client, storage_paths):
    response = client.post(
        "/api/parse",
        files={"file": ("invalid.bib", b"not bibtex", "text/plain")},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "No BibTeX entries were found in the uploaded file."
    metadata = json.loads(storage_paths["papers_file"].read_text(encoding="utf-8"))
    record = next(iter(metadata["papers"].values()))
    assert record["status"] == "failed"
    assert record["entry_count"] == 0


def test_verify_bib_returns_one_pdf_missing_result_per_entry(client):
    uploaded = _upload_bib(client).json()

    response = client.post(
        "/api/verify/bib",
        json={"bib_paper_id": uploaded["paper_id"], "source_paper_ids": []},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total_entries"] == 3
    assert body["matched_entries"] == 0
    assert len(body["results"]) == 3
    assert all(result["fields"][0]["status"] == "PDF_MISSING" for result in body["results"])


def test_verify_bib_uses_available_pdf_title_metadata(client):
    uploaded_bib = _upload_bib(client).json()
    pdf_content = make_test_pdf(
        "Attention Mechanisms in Deep Learning",
        "Smith, John and Doe, Jane",
        "Journal of Machine Learning Research",
        "2024",
        "doi: 10.1234/example",
    )
    uploaded_pdf = client.post(
        "/api/parse",
        files={
            "file": (
                "Attention Mechanisms in Deep Learning.pdf",
                pdf_content,
                "application/pdf",
            )
        },
    ).json()

    response = client.post(
        "/api/verify/bib",
        json={
            "bib_paper_id": uploaded_bib["paper_id"],
            "source_paper_ids": [uploaded_pdf["paper_id"]],
        },
    )

    assert response.status_code == 200
    result = response.json()["results"][0]
    statuses = {field["field_name"]: field["status"] for field in result["fields"]}
    assert statuses["title"] == "MATCH"
    assert statuses["year"] == "MATCH"
    assert statuses["authors"] == "MATCH"
    assert statuses["venue"] == "MATCH"
    assert statuses["doi"] == "BIB_MISSING"


def test_verify_unknown_bib_returns_404(client):
    response = client.post(
        "/api/verify/bib",
        json={"bib_paper_id": "does-not-exist", "source_paper_ids": []},
    )

    assert response.status_code == 404


def test_verify_rejects_pdf_as_bib_file(client):
    pdf_content = make_test_pdf("paper")
    uploaded_pdf = client.post(
        "/api/parse",
        files={"file": ("paper.pdf", pdf_content, "application/pdf")},
    ).json()

    response = client.post(
        "/api/verify/bib",
        json={"bib_paper_id": uploaded_pdf["paper_id"], "source_paper_ids": []},
    )

    assert response.status_code == 422
