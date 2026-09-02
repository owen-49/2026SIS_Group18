"""Tests for the Yi Parser to backend adapter."""

from pathlib import Path

import fitz
from backend.src.services import parser_adapter


def _make_two_page_pdf(path: Path) -> None:
    document = fitz.open()
    first_page = document.new_page()
    first_page.insert_text((72, 72), "Converted title", fontsize=20)
    first_page.insert_text((72, 115), "First page passage for parser matching.", fontsize=11)
    second_page = document.new_page()
    second_page.insert_text((72, 72), "Second section", fontsize=20)
    second_page.insert_text((72, 115), "Second page passage for parser matching.", fontsize=11)
    document.save(str(path))
    document.close()


def test_parse_document_adapts_converted_markdown(monkeypatch, tmp_path):
    pdf_path = tmp_path / "paper.pdf"
    output_dir = tmp_path / "markdown"
    _make_two_page_pdf(pdf_path)

    markdown = (
        "# Converted title\n\n"
        "First page passage for parser matching.\n\n"
        "![](figure.png)\n\n"
        "## Second section\n\n"
        "Second page passage for parser matching.\n"
    )

    def fake_convert(_pdf_path, output_dir=None, **_kwargs):
        assert output_dir == output_dir_expected
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "paper.md").write_text(markdown, encoding="utf-8")
        return markdown

    output_dir_expected = output_dir
    monkeypatch.setattr(parser_adapter, "convert_pdf_to_markdown", fake_convert)

    document = parser_adapter.parse_document(
        "paper-id",
        pdf_path,
        title="filename fallback",
        output_dir=output_dir,
    )

    assert document.paper_id == "paper-id"
    assert document.title == "Converted title"
    assert document.pages == 2
    assert [paragraph.text for paragraph in document.paragraphs] == [
        "Converted title",
        "First page passage for parser matching.",
        "Second section",
        "Second page passage for parser matching.",
    ]
    assert [(paragraph.page_start, paragraph.page_end) for paragraph in document.paragraphs] == [
        (1, 1),
        (1, 1),
        (2, 2),
        (2, 2),
    ]
