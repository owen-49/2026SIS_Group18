"""Tests for markdown_converter.py."""

from pathlib import Path

import fitz  # PyMuPDF
import pytest

from parser import markdown_converter as md_module
from parser.markdown_converter import (
    HybridBackendError,
    _deduplicate_image_references,
    convert_pdf_to_markdown,
    is_backend_reachable,
)

BACKEND_AVAILABLE = is_backend_reachable()


@pytest.fixture()
def sample_pdf(tmp_path: Path) -> Path:
    """A one-page PDF with a heading and a paragraph."""
    pdf_path = tmp_path / "sample.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "1 Introduction", fontsize=24)
    page.insert_text((72, 120), "This is a test paragraph for conversion.", fontsize=11)
    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


# ── Validation and error handling (no JVM/backend needed) ──────


class TestValidation:
    def test_missing_file_raises(self):
        with pytest.raises(FileNotFoundError):
            convert_pdf_to_markdown(Path("does-not-exist.pdf"))

    def test_non_pdf_suffix_raises(self, tmp_path: Path):
        bogus = tmp_path / "notes.txt"
        bogus.write_text("hello", encoding="utf-8")
        with pytest.raises(ValueError):
            convert_pdf_to_markdown(bogus)

    def test_unreachable_backend_raises(self, sample_pdf: Path):
        # Port 9 (discard) is closed, so the health check fails fast.
        with pytest.raises(HybridBackendError):
            convert_pdf_to_markdown(sample_pdf, hybrid_url="http://127.0.0.1:9")


# ── Image reference deduplication ──────────────────────────────


class TestImageDeduplication:
    def test_duplicated_refs_keep_last_occurrence(self):
        markdown = (
            "![](<img/a.png>)\n\n"
            "# Title\n\n"
            "Body text.\n\n"
            "![](<img/a.png>)\n\n"
            "![](<img/b.png>)\n"
        )
        result = _deduplicate_image_references(markdown)
        assert result.count("img/a.png") == 1
        assert result.index("img/a.png") > result.index("# Title")
        assert "img/b.png" in result

    def test_single_occurrences_are_untouched(self):
        markdown = "![](<img/a.png>)\n\nText.\n"
        assert _deduplicate_image_references(markdown) == markdown

    def test_text_without_images_is_unchanged(self):
        markdown = "# Title\n\nParagraph one.\n\nParagraph two.\n"
        assert _deduplicate_image_references(markdown) == markdown

    def test_mixed_text_and_image_line_is_kept(self):
        markdown = (
            "![](<img/a.png>)\n\n"
            "Figure 1: caption ![](<img/a.png>) text\n"
        )
        result = _deduplicate_image_references(markdown)
        assert result.count("img/a.png") == 1
        assert "Figure 1: caption" in result

    def test_more_than_two_occurrences_collapse_to_last(self):
        markdown = "![](<img/a.png>)\n\n![](<img/a.png>)\n\n![](<img/a.png>)\n"
        result = _deduplicate_image_references(markdown)
        assert result.count("img/a.png") == 1

    def test_plain_parenthesis_syntax_is_handled(self):
        markdown = "![](img/a.png)\n\nText.\n\n![](img/a.png)\n"
        result = _deduplicate_image_references(markdown)
        assert result.count("img/a.png") == 1


# ── Conversion tests ───────────────────────────────────────────


class TestLocalMode:
    def test_converts_and_returns_text(
        self, sample_pdf: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        # Redirect the default output dir so the test never clears the
        # repository's generated_markdown sample output.
        monkeypatch.setattr(md_module, "DEFAULT_OUTPUT_DIR", tmp_path / "generated")
        text = convert_pdf_to_markdown(sample_pdf, hybrid="off")
        assert "Introduction" in text
        assert "test paragraph" in text

    def test_output_file_kept_when_dir_given(self, sample_pdf: Path, tmp_path: Path):
        out_dir = tmp_path / "md"
        text = convert_pdf_to_markdown(sample_pdf, output_dir=out_dir, hybrid="off")
        assert (out_dir / "sample.md").exists()
        assert text == (out_dir / "sample.md").read_text(encoding="utf-8")


@pytest.mark.skipif(
    not BACKEND_AVAILABLE,
    reason="hybrid backend not running on localhost:5002",
)
class TestHybridMode:
    def test_converts_with_default_backend(self, sample_pdf: Path):
        text = convert_pdf_to_markdown(sample_pdf)
        assert "Introduction" in text
        assert "test paragraph" in text
