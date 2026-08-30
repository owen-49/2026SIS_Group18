"""Tests for the real Parser-to-backend adapter."""

from backend.src.services.parser_adapter import parse_document
from backend.tests.pdf_fixtures import make_test_pdf


def test_parse_document_uses_real_parser_and_preserves_metadata(tmp_path):
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(
        make_test_pdf(
            "Attention Mechanisms in Deep Learning",
            "Smith, John and Doe, Jane",
            "Journal of Machine Learning Research",
            "2024",
            "doi: 10.1234/example",
            "Self-attention removes the need for recurrence.",
        )
    )

    document = parse_document("paper-id", pdf_path)

    assert document.paper_id == "paper-id"
    assert document.title == "Attention Mechanisms in Deep Learning"
    assert document.authors == ["Smith, John", "Doe, Jane"]
    assert document.year == 2024
    assert document.venue == "Journal of Machine Learning Research"
    assert document.doi == "10.1234/example"
    assert document.pages == 1
    assert document.paragraphs
    assert "Self-attention" in document.paragraphs[0].text


def test_parse_document_preserves_single_last_first_author(tmp_path):
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(
        make_test_pdf(
            "A Paper With One Author",
            "Smith, John",
            "Journal of Example Research",
            "2024",
        )
    )

    document = parse_document("paper-id", pdf_path)

    assert document.authors == ["Smith, John"]
