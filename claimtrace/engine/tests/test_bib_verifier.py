"""Tests for bib_verifier.py."""

import pytest

from engine.src.bib_parser import BibEntry, parse_bib_text
from engine.src.bib_verifier import (
    BibVerificationResult,
    FieldStatus,
    PdfMetadata,
    verify_all_entries,
    verify_bib_against_pdf,
)

# ── Fixtures ────────────────────────────────────────────────


@pytest.fixture
def perfect_bib_entry():
    return BibEntry(
        key="smith2024attention",
        entry_type="article",
        title="Attention Mechanisms in Deep Learning",
        authors=["Smith, John", "Doe, Jane"],
        year=2024,
        venue="Journal of Machine Learning Research",
        doi="10.1234/jmlr.2024.42",
    )


@pytest.fixture
def perfect_pdf_meta():
    return PdfMetadata(
        title="Attention Mechanisms in Deep Learning",
        authors=["Smith, John", "Doe, Jane"],
        year=2024,
        venue="Journal of Machine Learning Research",
        doi="10.1234/jmlr.2024.42",
    )


# ── Happy path ──────────────────────────────────────────────


class TestPerfectMatch:
    def test_all_fields_match(self, perfect_bib_entry, perfect_pdf_meta):
        result = verify_bib_against_pdf(perfect_bib_entry, perfect_pdf_meta)
        assert not result.has_errors
        assert result.error_count == 0
        assert all(
            f.status == FieldStatus.MATCH
            for f in result.fields
            if f.field_name != "venue"  # venue not checked when both match
        )

    def test_summary_clean(self, perfect_bib_entry, perfect_pdf_meta):
        result = verify_bib_against_pdf(perfect_bib_entry, perfect_pdf_meta)
        assert "match" in result.summary.lower()


# ── Mismatch detection ──────────────────────────────────────


class TestTitleMismatch:
    def test_subtle_typo(self, perfect_bib_entry, perfect_pdf_meta):
        perfect_pdf_meta.title = "Attention Mechanims in Deep Learning"  # typo
        result = verify_bib_against_pdf(perfect_bib_entry, perfect_pdf_meta)
        title_result = next(f for f in result.fields if f.field_name == "title")
        assert title_result.status == FieldStatus.MISMATCH

    def test_case_difference_is_match(self, perfect_bib_entry, perfect_pdf_meta):
        perfect_pdf_meta.title = "attention mechanisms in deep learning"
        result = verify_bib_against_pdf(perfect_bib_entry, perfect_pdf_meta)
        title_result = next(f for f in result.fields if f.field_name == "title")
        assert title_result.status == FieldStatus.MATCH


class TestYearMismatch:
    def test_wrong_year(self, perfect_bib_entry, perfect_pdf_meta):
        perfect_pdf_meta.year = 2023
        result = verify_bib_against_pdf(perfect_bib_entry, perfect_pdf_meta)
        year_result = next(f for f in result.fields if f.field_name == "year")
        assert year_result.status == FieldStatus.MISMATCH
        assert "difference" in year_result.detail

    def test_year_missing_in_bib(self, perfect_bib_entry, perfect_pdf_meta):
        perfect_bib_entry.year = None
        result = verify_bib_against_pdf(perfect_bib_entry, perfect_pdf_meta)
        year_result = next(f for f in result.fields if f.field_name == "year")
        assert year_result.status == FieldStatus.BIB_MISSING


class TestAuthorMismatch:
    def test_first_author_differs(self, perfect_bib_entry, perfect_pdf_meta):
        perfect_pdf_meta.authors = ["Different, Person", "Doe, Jane"]
        result = verify_bib_against_pdf(perfect_bib_entry, perfect_pdf_meta)
        author_result = next(f for f in result.fields if f.field_name == "authors")
        assert author_result.status == FieldStatus.MISMATCH
        assert "First author differs" in author_result.detail


class TestDOIMismatch:
    def test_doi_points_to_different_paper(self, perfect_bib_entry, perfect_pdf_meta):
        perfect_pdf_meta.doi = "10.9999/wrong-paper.2024"
        result = verify_bib_against_pdf(perfect_bib_entry, perfect_pdf_meta)
        doi_result = next(f for f in result.fields if f.field_name == "doi")
        assert doi_result.status == FieldStatus.MISMATCH


# ── Missing metadata handling ───────────────────────────────


class TestMissingFields:
    def test_pdf_missing_title(self, perfect_bib_entry, perfect_pdf_meta):
        perfect_pdf_meta.title = ""
        result = verify_bib_against_pdf(perfect_bib_entry, perfect_pdf_meta)
        title_result = next(f for f in result.fields if f.field_name == "title")
        assert title_result.status == FieldStatus.PDF_MISSING

    def test_bib_missing_authors(self, perfect_bib_entry, perfect_pdf_meta):
        perfect_bib_entry.authors = []
        result = verify_bib_against_pdf(perfect_bib_entry, perfect_pdf_meta)
        author_result = next(f for f in result.fields if f.field_name == "authors")
        assert author_result.status == FieldStatus.BIB_MISSING


# ── Batch verification ──────────────────────────────────────


class TestBatchVerifyAllEntries:
    def test_all_matched(self, perfect_bib_entry, perfect_pdf_meta):
        results = verify_all_entries(
            [perfect_bib_entry],
            {"smith2024attention": perfect_pdf_meta},
        )
        assert len(results) == 1
        assert not results[0].has_errors

    def test_missing_pdf(self):
        entry = BibEntry(key="orphan2023", title="Orphan Paper", year=2023)
        results = verify_all_entries([entry], {})
        assert len(results) == 1
        assert results[0].fields[0].status == FieldStatus.PDF_MISSING
