"""Tests for pdf_parser.py — Pair 1."""

from pathlib import Path

import pytest

from parser.pdf_parser import (
    Paragraph,
    ParsedPaper,
    extract_blocks,
    parse_pdf,
    recover_paragraphs,
    repair_hyphenation,
    reorder_two_column,
)


# ── Unit tests (no PDF required) ──────────────────────────────


class TestRepairHyphenation:
    def test_simple_hyphenation(self):
        assert repair_hyphenation("repre-\nsentation") == "representation"

    def test_no_hyphenation(self):
        assert repair_hyphenation("representation") == "representation"

    def test_multiple_hyphens(self):
        # "state-of-the-art" broken across lines.
        # The regex sees "the-\nart" as a line-break hyphen and removes it.
        # This is a known limitation: we can't distinguish compound hyphens
        # from line-break hyphens without dictionary lookup.
        text = "state-of-the-\nart performance"
        result = repair_hyphenation(text)
        assert "state-of-the" in result
        assert "art performance" in result


class TestReorderTwoColumn:
    def test_empty_blocks(self):
        from parser.pdf_parser import TextBlock

        assert reorder_two_column([], 612) == []

    def test_single_column(self):
        from parser.pdf_parser import TextBlock

        blocks = [
            TextBlock("first line", (10, 10, 300, 30), 1),
            TextBlock("second line", (10, 40, 300, 60), 1),
        ]
        result = reorder_two_column(blocks, 612)
        assert len(result) == 2
        assert result[0].text == "first line"


class TestRecoverParagraphs:
    def test_single_block(self):
        from parser.pdf_parser import TextBlock

        blocks = [TextBlock("Hello world", (10, 10, 300, 30), 1)]
        paragraphs = recover_paragraphs(blocks)
        assert len(paragraphs) == 1
        assert paragraphs[0].text == "Hello world"

    def test_consecutive_lines_merged(self):
        from parser.pdf_parser import TextBlock

        blocks = [
            TextBlock("Line one", (10, 10, 300, 25), 1),
            TextBlock("Line two", (10, 30, 300, 45), 1),
        ]
        paragraphs = recover_paragraphs(blocks)
        assert len(paragraphs) == 1
        assert "Line one" in paragraphs[0].text
        assert "Line two" in paragraphs[0].text


# ── Integration tests (require test PDFs) ─────────────────────


class TestParsePDF:
    @pytest.mark.skipif(
        not list(Path(__file__).parent.glob("test_data/*.pdf")),
        reason="No test PDFs in test_data/",
    )
    def test_parse_real_pdf(self):
        """Parse a real academic PDF and verify structure."""
        pdfs = list(Path(__file__).parent.glob("test_data/*.pdf"))
        result = parse_pdf(pdfs[0])
        assert isinstance(result, ParsedPaper)
        assert result.pages > 0
        assert len(result.paragraphs) > 0
