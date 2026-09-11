"""Resolve a citation marker to the parsed paper it points at.

This is the backend half of the Engine's ``SourceResolver`` contract, described
in ``docs/engine-source-resolver-handoff.md`` (Part 1). ``SourceResolver`` is
deliberately storage-agnostic — the caller injects ``locate`` and ``parse`` —
and this module supplies those two callables from persisted Parser output:

    CitationLookup --> locate_source() --> SourcePaper --> parse_source() --> [passage, ...]

Two deliberate design notes:

* **Markers, not keys.** ``locate_source`` is typed on a citation *key*, but a
  caller may pass the raw marker as extracted (``\\cite{wei2022emergent}``,
  ``(Wei, 2022)``, ``[1]``); normalisation happens inside ``look_up_citation``
  and the resolved key is reported back on the lookup. Manuscripts do not carry
  clean BibTeX keys for numeric or author-year markers, so accepting raw markers
  is the only contract that works for all three marker styles.
* **Reuse, not reimplementation.** Resolution delegates to the private helpers
  in :mod:`backend.src.services.analysis_service` so that a claim's
  ``cited_source`` is identical whether it came from ``GET /api/papers/{id}/claims``
  or from a comparison. Those helpers are private to a sibling module; promoting
  them to public names is tracked as follow-up work.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - annotations only
    from engine.source_resolver import SourcePaper

from ..models import ComparisonStatus, IdentifiedSource, PaperRecord, ParseStatus
from ..storage.paper_store import PaperStoreError, list_papers
from .analysis_service import (
    _NUMERIC_CITATION_RE,
    _YEAR_RE,
    AnalysisServiceError,
    _citation_keys,
    _find_bib_entry,
    _first_author_surname,
    _load_bibliography_entries,
    _load_completed_pdf,
    _load_completed_pdf_catalog,
    _LoadedPdf,
    _match_pdf_to_bib_entry,
    _normalise_text,
    _source_from_bib,
    _tokens,
)


class SourceLocatorError(RuntimeError):
    """Raised when the paper library itself cannot be read."""


@dataclass(frozen=True)
class CitationLookup:
    """Everything the comparison service needs to know about one marker.

    ``outcome`` is ``ComparisonStatus.COMPARED`` exactly when ``source`` is a
    usable parsed PDF; every other value explains why no comparison is possible.
    """

    marker: str
    outcome: ComparisonStatus
    message: str
    citation_key: str | None = None
    cited_source: IdentifiedSource | None = None
    source: _LoadedPdf | None = None

    @property
    def resolved(self) -> bool:
        """Whether a parsed source PDF was found for this marker."""
        return self.source is not None


def source_passages(loaded: _LoadedPdf) -> list[str]:
    """Return the source paper's passages, one per parsed paragraph.

    **The 1:1 invariant.** The returned list is positionally identical to
    ``loaded.parsed.paragraphs`` — no paragraph is dropped, reordered or merged.
    ``Retriever.build_index`` stores this list verbatim and
    ``RetrievalResult.passage_index`` is an index into it, so *that index is a
    paragraph index* and is what gives evidence its page number and display
    location. Adding any filtering here would silently shift every page
    attribution in the response rather than raise.

    Text is whitespace-normalised for display; normalisation rewrites a string
    in place and does not move it.
    """
    return [_normalise_text(paragraph.text) for paragraph in loaded.parsed.paragraphs]


def locate_source(
    citation_key: str,
    *,
    lookup: CitationLookup | None = None,
) -> SourcePaper | None:
    """Return the ``SourcePaper`` for a citation, or ``None`` if unavailable.

    This is the Engine's ``locate`` callable. Pass ``lookup`` to adapt an
    already-performed lookup without touching storage again; omit it and the
    library is searched for ``citation_key``.
    """
    from engine.source_resolver import SourcePaper

    if lookup is None:
        lookup = look_up_citation(citation_key)
    if lookup.source is None:
        return None

    loaded = lookup.source
    title = (
        loaded.parsed.title
        or loaded.record.title
        or loaded.record.original_filename
    )
    return SourcePaper(
        source_id=loaded.record.paper_id,
        title=title,
        metadata={"passages": source_passages(loaded), "citation_key": lookup.citation_key},
    )


def parse_source(source_paper: SourcePaper) -> list[str]:
    """Return the passages ``locate_source`` attached to a ``SourcePaper``.

    This is the Engine's ``parse`` callable. It is pure — the passages were read
    from the persisted parsed document during ``locate_source``, because
    re-parsing a PDF in-request would need the OpenDataLoader/JDK toolchain and
    take minutes. A paper whose parse never completed cannot enter the catalog,
    so it surfaces as ``SOURCE_NOT_AVAILABLE`` instead.
    """
    return list(source_paper.metadata.get("passages") or [])


def _candidate_count(marker: str, entries: list[Any]) -> int:
    """Count the entries ``_find_bib_entry`` considered, for messaging only.

    Never used to resolve anything — resolution is ``_find_bib_entry``'s job, and
    this mirrors its two branches purely so that "no such reference" and "several
    references match" can be reported as different statuses. If this drifts from
    the resolver the worst case is a less precise message, never a wrong source.
    """
    clean_marker = marker.strip("()[]【】 ")
    keys = {key.casefold() for key in _citation_keys(marker)}
    if clean_marker:
        keys.add(clean_marker.casefold())

    direct = sum(1 for entry in entries if entry.key.casefold() in keys)
    if direct:
        return direct

    year_match = _YEAR_RE.search(marker)
    if not year_match:
        return 0
    year = int(year_match.group(0))
    marker_tokens = _tokens(marker)
    return sum(
        1
        for entry in entries
        if entry.year == year
        and _first_author_surname(entry.authors)
        and _first_author_surname(entry.authors) in marker_tokens
    )


def _fallback_key(marker: str) -> str:
    """Return a key-shaped stand-in when the matched entry carries no key.

    A malformed ``.bib`` can yield an empty ``key``; reporting an empty citation
    key would leave the caller with nothing to display or re-query with, so the
    marker is reused with its surrounding citation punctuation removed.
    """
    return marker.strip("()[]【】 ") or marker


def _load_source_catalog(
    records: list[PaperRecord],
    *,
    exclude_paper_id: str | None,
) -> tuple[list[_LoadedPdf], int]:
    """Load usable source PDFs, isolating papers with unreadable parse output.

    ``analysis_service._load_completed_pdf_catalog`` aborts on the first record
    whose parsed JSON cannot be read, which would make one corrupt upload break
    comparisons for every other paper. The healthy path is delegated unchanged;
    only when that raises is the catalog rebuilt record by record, skipping the
    unreadable ones so the caller can report them instead of failing outright.
    """
    try:
        return _load_completed_pdf_catalog(records, exclude_paper_id=exclude_paper_id), 0
    except AnalysisServiceError:
        catalog: list[_LoadedPdf] = []
        skipped = 0
        for record in records:
            if (
                record.file_type != "pdf"
                or record.paper_id == exclude_paper_id
                or record.status != ParseStatus.COMPLETED
                or not record.parsed_result_path
            ):
                continue
            try:
                catalog.append(_load_completed_pdf(record))
            except AnalysisServiceError:
                skipped += 1
        return catalog, skipped


def look_up_citation(
    marker: str,
    *,
    exclude_paper_id: str | None = None,
) -> CitationLookup:
    """Map a citation marker to a parsed source paper in the local library.

    Status precedence is fixed so the same marker always yields the same answer
    regardless of library contents: an unresolvable *marker form* is reported
    before a missing bibliography, which is reported before a missing reference.

    Args:
        marker: The citation marker exactly as extracted from the manuscript.
        exclude_paper_id: A manuscript to leave out of the source catalog, so a
            paper cannot be used as the source for its own claim.

    Raises:
        SourceLocatorError: The paper library could not be listed.
    """
    clean_marker = _normalise_text(marker)
    if not clean_marker:
        return CitationLookup(
            marker=marker,
            outcome=ComparisonStatus.MARKER_UNSUPPORTED,
            message="No citation marker was supplied.",
        )

    try:
        records = list_papers()
    except PaperStoreError as exc:
        raise SourceLocatorError("Unable to read paper metadata.") from exc

    # A numeric label is a position in the manuscript's own reference list, not a
    # BibTeX key and not an index into the uploaded bibliography, so it can never
    # be resolved locally. Checked before the bibliography so the answer does not
    # depend on what happens to be uploaded.
    if _NUMERIC_CITATION_RE.fullmatch(clean_marker):
        return CitationLookup(
            marker=clean_marker,
            outcome=ComparisonStatus.MARKER_UNSUPPORTED,
            message=(
                f"The numeric marker '{clean_marker}' does not identify a bibliography "
                "entry. Supply the reference's BibTeX key instead."
            ),
        )

    entries = _load_bibliography_entries(records)
    if not entries:
        return CitationLookup(
            marker=clean_marker,
            outcome=ComparisonStatus.NO_BIBLIOGRAPHY,
            message=(
                "No single completed .bib upload was found to resolve citations "
                "against. Upload the manuscript's bibliography."
            ),
        )

    entry = _find_bib_entry(clean_marker, entries)
    if entry is None:
        count = _candidate_count(clean_marker, entries)
        if count > 1:
            return CitationLookup(
                marker=clean_marker,
                outcome=ComparisonStatus.REFERENCE_AMBIGUOUS,
                message=(
                    f"{count} bibliography entries match '{clean_marker}'. "
                    "Resolve it to a single BibTeX key."
                ),
            )
        return CitationLookup(
            marker=clean_marker,
            outcome=ComparisonStatus.REFERENCE_NOT_FOUND,
            message=f"No bibliography entry matches '{clean_marker}'.",
        )

    catalog, skipped = _load_source_catalog(records, exclude_paper_id=exclude_paper_id)
    citation_key = entry.key or _fallback_key(clean_marker)
    source_pdf = _match_pdf_to_bib_entry(entry, catalog)
    cited_source = _source_from_bib(
        entry,
        citation_key,
        source_pdf.record.paper_id if source_pdf else None,
    )

    if source_pdf is None:
        reason = f"No parsed PDF in the library matches '{citation_key}'."
        if skipped:
            reason += f" ({skipped} paper(s) were skipped as unreadable.)"
        return CitationLookup(
            marker=clean_marker,
            outcome=ComparisonStatus.SOURCE_NOT_AVAILABLE,
            message=reason,
            citation_key=citation_key,
            cited_source=cited_source,
        )

    message = f"Resolved '{citation_key}' to a parsed source paper."
    if skipped:
        message += f" ({skipped} other paper(s) were skipped as unreadable.)"
    return CitationLookup(
        marker=clean_marker,
        outcome=ComparisonStatus.COMPARED,
        message=message,
        citation_key=citation_key,
        cited_source=cited_source,
        source=source_pdf,
    )
