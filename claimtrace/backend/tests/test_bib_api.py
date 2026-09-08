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
    body = response.json()
    assert body["status"] == "completed"
    assert body["file_type"] == "bib"
    assert body["entry_count"] == 3
    assert [entry["key"] for entry in body["entries"]] == [
        "attention2024",
        "retrieval2023",
        "metadata2022",
    ]
    assert body["entries"][0]["authors"] == ["Smith, John", "Doe, Jane"]


def test_parse_bib_response_changes_with_persisted_upload(client):
    bib = b"""
@article{different2025,
  title={A Different Paper},
  author={Taylor, Alex},
  year={2025},
  journal={Journal of Different Results}
}
"""
    uploaded = client.post(
        "/api/parse",
        files={"file": ("different.bib", bib, "text/plain")},
    ).json()

    response = client.post(
        "/api/parse/bib",
        json={"paper_id": uploaded["paper_id"]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["entry_count"] == 1
    assert body["entries"] == [
        {
            "key": "different2025",
            "entry_type": "article",
            "title": "A Different Paper",
            "authors": ["Taylor, Alex"],
            "year": 2025,
            "venue": "Journal of Different Results",
            "volume": "",
            "number": "",
            "pages": "",
            "doi": "",
            "url": "",
            "publisher": "",
            "raw_text": (
                "@article{different2025,\n"
                "  title={A Different Paper},\n"
                "  author={Taylor, Alex},\n"
                "  year={2025},\n"
                "  journal={Journal of Different Results}\n"
                "}"
            ),
        }
    ]


def test_replace_bib_reuses_paper_id_and_does_not_create_duplicate(client, storage_paths):
    uploaded = _upload_bib(client).json()
    replacement = b"""
@article{updated2025,
  title={Updated Citation Record},
  author={Smith, John},
  year={2025},
  journal={Journal of Updated Research}
}
"""

    response = client.put(
        f"/api/parse/{uploaded['paper_id']}",
        files={"file": ("references.bib", replacement, "text/plain")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["paper_id"] == uploaded["paper_id"]
    assert body["status"] == "completed"
    assert body["entry_count"] == 1

    papers = client.get("/api/papers").json()
    assert papers["total"] == 1
    assert papers["papers"][0]["paper_id"] == uploaded["paper_id"]
    assert papers["papers"][0]["file_size"] == len(replacement)

    stored_file = storage_paths["upload_dir"] / f"{uploaded['paper_id']}.bib"
    assert stored_file.read_bytes() == replacement
    parsed = load_bib_document(storage_paths["bib_parsed_dir"] / f"{uploaded['paper_id']}.json")
    assert [entry.key for entry in parsed.entries] == ["updated2025"]


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
