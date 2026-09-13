"""Unit tests for citation-marker resolution against the local paper library.

No LLM, no retriever, no network: these exercise ``look_up_citation`` and the
``locate_source``/``parse_source`` facade directly.
"""

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from pathlib import Path

import pytest
from backend.src.models import (
    BibEntryRecord,
    ComparisonStatus,
    PaperRecord,
    ParsedBibDocument,
    ParsedDocument,
    ParsedParagraph,
    ParseStatus,
)
from backend.src.services import source_locator
from backend.src.services.source_locator import (
    SourceLocatorError,
    locate_source,
    look_up_citation,
    parse_source,
)
from backend.src.storage.bib_document_store import save_bib_document
from backend.src.storage.paper_store import PaperStoreError, create_paper
from backend.src.storage.parsed_document_store import save_parsed_document

PASSAGES = [
    "Self-attention enables the model to relate information from different positions "
    "without recurrence.",
    "The experiment evaluates citation verification quality using source passages.",
]


def _record(paper_id: str, file_type: str, *, parsed_path: Path | None = None) -> PaperRecord:
    now = datetime.now(UTC)
    suffix = "bib" if file_type == "bib" else "pdf"
    return PaperRecord(
        paper_id=paper_id,
        original_filename=f"{paper_id}.{suffix}",
        stored_filename=f"{paper_id}.{suffix}",
        file_path=f"/uploads/{paper_id}",
        parsed_result_path=str(parsed_path) if parsed_path else None,
        file_type=file_type,
        file_size=100,
        status=ParseStatus.COMPLETED,
        pages=1,
        created_at=now,
        updated_at=now,
    )


def _add_source_pdf(paper_id: str, *, title: str, doi: str | None = None, text=None) -> str:
    """Persist one completed parsed source PDF and return its paper ID."""
    document = ParsedDocument(
        paper_id=paper_id,
        title=title,
        authors=["Smith, Jane"],
        year=2024,
        venue="Journal of Retrieval",
        doi=doi,
        pages=1,
        paragraphs=[
            ParsedParagraph(text=chunk, page_start=1, page_end=1)
            for chunk in (text if text is not None else PASSAGES)
        ],
    )
    path = save_parsed_document(document)
    create_paper(_record(paper_id, "pdf", parsed_path=path))
    return paper_id


def _add_bibliography(entries: list[BibEntryRecord], paper_id: str = "bib-1") -> str:
    """Persist one completed .bib — the resolver only trusts a single one."""
    path = save_bib_document(ParsedBibDocument(paper_id=paper_id, entries=entries))
    create_paper(_record(paper_id, "bib", parsed_path=path))
    return paper_id


def _entry(
    key: str,
    *,
    title: str,
    authors=("Smith, Jane",),
    year: int | None = 2024,
    doi: str = "",
) -> BibEntryRecord:
    return BibEntryRecord(
        key=key, title=title, authors=list(authors), year=year, doi=doi
    )


@pytest.fixture()
def library(storage_paths):
    """A bibliography whose single reference points at a parsed PDF."""
    del storage_paths
    _add_source_pdf("pdf-1", title="Retrieval with citations", doi="10.1234/example")
    _add_bibliography([_entry("smith2024", title="Retrieval with citations")])


# ── Marker resolution --------------------------------------------


def test_latex_marker_resolves_to_the_parsed_pdf(library):
    lookup = look_up_citation("\\cite{smith2024}")

    assert lookup.outcome is ComparisonStatus.COMPARED
    assert lookup.resolved is True
    assert lookup.citation_key == "smith2024"
    assert lookup.source.record.paper_id == "pdf-1"
    assert lookup.cited_source.source_paper_id == "pdf-1"
    assert lookup.cited_source.title == "Retrieval with citations"


def test_bare_key_is_equivalent_to_the_latex_marker(library):
    lookup = look_up_citation("smith2024")

    assert lookup.outcome is ComparisonStatus.COMPARED
    assert lookup.citation_key == "smith2024"


def test_author_year_marker_resolves_through_the_year_and_surname_branch(library):
    lookup = look_up_citation("(Smith, 2024)")

    assert lookup.outcome is ComparisonStatus.COMPARED
    assert lookup.citation_key == "smith2024"


def test_unknown_key_is_reference_not_found(library):
    lookup = look_up_citation("\\cite{nobody1999}")

    assert lookup.outcome is ComparisonStatus.REFERENCE_NOT_FOUND
    assert lookup.resolved is False
    assert lookup.source is None
    assert lookup.cited_source is None


def test_two_entries_matching_one_author_year_are_reported_as_ambiguous(storage_paths):
    del storage_paths
    _add_source_pdf("pdf-1", title="Retrieval with citations")
    _add_bibliography(
        [
            _entry("smith2024a", title="Retrieval with citations"),
            _entry("smith2024b", title="Citation verification at scale"),
        ]
    )

    lookup = look_up_citation("(Smith, 2024)")

    # Ambiguity is never guessed at: the resolver refuses rather than picking one.
    assert lookup.outcome is ComparisonStatus.REFERENCE_AMBIGUOUS
    assert lookup.cited_source is None


def test_duplicate_key_across_the_bibliography_is_ambiguous():
    entries = [_entry("one", title="First paper"), _entry("one", title="Second paper")]

    assert source_locator._candidate_count("\\cite{one}", entries) == 2


def test_numeric_marker_is_unsupported_even_with_a_bibliography(library):
    for marker in ("[1]", "[1, 2]", "【3】"):
        lookup = look_up_citation(marker)
        assert lookup.outcome is ComparisonStatus.MARKER_UNSUPPORTED, marker
        assert lookup.citation_key is None


def test_blank_marker_is_unsupported(library):
    assert look_up_citation("   ").outcome is ComparisonStatus.MARKER_UNSUPPORTED


def test_numeric_marker_answers_the_same_way_with_no_bibliography(storage_paths):
    """Status precedence must not depend on what happens to be uploaded."""
    del storage_paths

    assert look_up_citation("[1]").outcome is ComparisonStatus.MARKER_UNSUPPORTED


# ── Library-level failures ---------------------------------------


def test_missing_bibliography_is_reported_separately(storage_paths):
    del storage_paths
    _add_source_pdf("pdf-1", title="Retrieval with citations")

    assert look_up_citation("\\cite{smith2024}").outcome is ComparisonStatus.NO_BIBLIOGRAPHY


def test_several_bibliographies_are_not_guessed_between(storage_paths):
    del storage_paths
    entries = [_entry("smith2024", title="Retrieval with citations")]
    _add_source_pdf("pdf-1", title="Retrieval with citations")
    _add_bibliography(entries, "bib-1")
    _add_bibliography(entries, "bib-2")

    assert look_up_citation("\\cite{smith2024}").outcome is ComparisonStatus.NO_BIBLIOGRAPHY


def test_reference_without_a_matching_local_pdf_is_source_not_available(storage_paths):
    del storage_paths
    _add_source_pdf("pdf-1", title="Entirely different work", doi="10.9999/other")
    _add_bibliography([_entry("smith2024", title="Retrieval with citations")])

    lookup = look_up_citation("\\cite{smith2024}")

    assert lookup.outcome is ComparisonStatus.SOURCE_NOT_AVAILABLE
    # Bibliography metadata is still worth returning even with no PDF behind it.
    assert lookup.citation_key == "smith2024"
    assert lookup.cited_source.title == "Retrieval with citations"
    assert lookup.source is None


def test_a_paper_is_never_the_source_for_its_own_claim(library):
    lookup = look_up_citation("\\cite{smith2024}", exclude_paper_id="pdf-1")

    assert lookup.outcome is ComparisonStatus.SOURCE_NOT_AVAILABLE


def test_unreadable_parsed_json_does_not_hide_the_healthy_paper(library, storage_paths):
    """One corrupt upload must not break comparisons for every other paper."""
    broken_path = storage_paths["parsed_dir"] / "pdf-broken.json"
    broken_path.write_text("{not json", encoding="utf-8")
    create_paper(_record("pdf-broken", "pdf", parsed_path=broken_path))

    lookup = look_up_citation("\\cite{smith2024}")

    assert lookup.outcome is ComparisonStatus.COMPARED
    assert lookup.source.record.paper_id == "pdf-1"
    assert "skipped as unreadable" in lookup.message


def test_only_unreadable_papers_reports_source_not_available(storage_paths):
    broken_path = storage_paths["parsed_dir"] / "pdf-broken.json"
    broken_path.parent.mkdir(parents=True, exist_ok=True)
    broken_path.write_text("{not json", encoding="utf-8")
    create_paper(_record("pdf-broken", "pdf", parsed_path=broken_path))
    _add_bibliography([_entry("smith2024", title="Retrieval with citations")])

    lookup = look_up_citation("\\cite{smith2024}")

    assert lookup.outcome is ComparisonStatus.SOURCE_NOT_AVAILABLE
    assert "skipped as unreadable" in lookup.message


def test_paper_store_failure_is_raised_not_swallowed(monkeypatch):
    def unreadable_store(*args, **kwargs):
        raise PaperStoreError("unreadable store")

    monkeypatch.setattr(source_locator, "list_papers", unreadable_store)

    with pytest.raises(SourceLocatorError):
        look_up_citation("\\cite{smith2024}")


# ── locate_source / parse_source facade ---------------------------


def test_facade_round_trip_preserves_one_passage_per_paragraph(library):
    lookup = look_up_citation("\\cite{smith2024}")
    source = locate_source("smith2024", lookup=lookup)

    assert source.source_id == "pdf-1"
    assert source.title == "Retrieval with citations"

    passages = parse_source(source)
    # The 1:1 invariant is what makes RetrievalResult.passage_index a paragraph
    # index, and therefore what makes each evidence page number correct.
    assert len(passages) == len(lookup.source.parsed.paragraphs)
    assert passages == PASSAGES


def test_facade_returns_none_for_an_unresolvable_marker(library):
    assert locate_source("\\cite{nobody1999}") is None


def test_parse_source_tolerates_a_source_paper_without_passages():
    from engine.source_resolver import SourcePaper

    assert parse_source(SourcePaper(source_id="x")) == []


def test_blank_paragraphs_are_normalised_but_never_dropped(storage_paths):
    """Dropping one would shift every later passage's index and its page."""
    del storage_paths
    _add_source_pdf(
        "pdf-1",
        title="Whitespace heavy",
        text=["First   paragraph\nwith breaks.", "   ", "Third paragraph."],
    )
    _add_bibliography([_entry("smith2024", title="Whitespace heavy")])

    lookup = look_up_citation("\\cite{smith2024}")
    passages = parse_source(locate_source("smith2024", lookup=lookup))

    assert passages == ["First paragraph with breaks.", "", "Third paragraph."]


def test_upstream_helpers_this_module_depends_on_still_exist():
    """This module deliberately reuses private analysis_service helpers."""
    from backend.src.services import analysis_service

    for name in (
        "_load_completed_pdf_catalog",
        "_load_bibliography_entries",
        "_load_completed_pdf",
        "_find_bib_entry",
        "_match_pdf_to_bib_entry",
        "_source_from_bib",
        "_citation_keys",
        "_normalise_text",
    ):
        assert hasattr(analysis_service, name), name


def test_lookup_is_immutable(library):
    lookup = look_up_citation("\\cite{smith2024}")

    with pytest.raises(FrozenInstanceError):
        lookup.marker = "other"


def test_citation_key_falls_back_to_the_marker_when_the_entry_has_no_key(storage_paths):
    """R6: a malformed .bib can carry an empty key; never emit a blank one."""
    del storage_paths
    _add_source_pdf("pdf-1", title="Untitled entry")
    _add_bibliography([_entry("", title="Untitled entry")])

    lookup = look_up_citation("(Smith, 2024)")

    assert lookup.outcome is ComparisonStatus.COMPARED
    assert lookup.citation_key == "Smith, 2024"
