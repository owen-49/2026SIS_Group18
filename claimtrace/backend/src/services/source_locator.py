"""Resolve a citation marker to the parsed paper it points at.

This is the backend half of the Engine's ``SourceResolver`` contract. That
contract is deliberately storage-agnostic — the caller injects ``locate`` and
``parse`` —
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

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - annotations only
    from engine.source_resolver import SourcePaper

from ..models import AuditRequest, ComparisonStatus, IdentifiedSource, PaperRecord, ParseStatus
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
from .paper_lifecycle import paper_lifecycle_lock
from .reference_input_service import AuditInputError, load_audit_references


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


@dataclass
class CitationLookupContext:
    """Inputs shared by all citation lookups in one manuscript request.

    A manuscript commonly contains many distinct citation markers. Loading the
    same reference artifact and parsed-PDF catalog for every marker makes
    ``GET /papers/{id}/claims`` scale with the number of citations instead of
    with the number of uploaded papers. The context is deliberately request
    scoped: paper uploads/deletions remain visible on the next request and no
    mutable process-wide cache is introduced.
    """

    records: list[PaperRecord]
    exclude_paper_id: str | None
    bib_paper_id: str | None
    manuscript_references: list[Any] | None = None
    manuscript_error: tuple[str, str] | None = None
    bibliography_references: list[Any] | None = None
    bibliography_entries: list[Any] | None = None
    bibliography_error: tuple[str, str] | None = None
    source_catalog: list[_LoadedPdf] = field(default_factory=list)
    skipped_source_count: int = 0


def _is_single_numeric_marker(marker: str) -> bool:
    return bool(re.fullmatch(r"[\[【]\s*\d+\s*[\]】]", marker))


def _uses_manuscript_references(
    marker: str,
    *,
    exclude_paper_id: str | None,
    bib_paper_id: str | None,
) -> bool:
    """Whether a marker needs the manuscript's persisted reference list."""
    if _NUMERIC_CITATION_RE.fullmatch(marker):
        return True
    return bool(
        exclude_paper_id and not bib_paper_id and marker.startswith("(") and _YEAR_RE.search(marker)
    )


def _load_reference_input(
    request: AuditRequest,
    *,
    lock_id: str,
) -> tuple[list[Any] | None, tuple[str, str] | None]:
    """Load one reference input and retain an API-safe error for its callers."""
    try:
        with paper_lifecycle_lock(lock_id):
            _, _, references, _ = load_audit_references(request)
    except AuditInputError as exc:
        return None, (exc.code, str(exc))
    return references, None


def build_citation_lookup_context(
    markers: list[str],
    *,
    exclude_paper_id: str | None,
    bib_paper_id: str | None = None,
) -> CitationLookupContext:
    """Prepare all shared lookup inputs once for a claims response."""
    try:
        records = list_papers()
    except PaperStoreError as exc:
        raise SourceLocatorError("Unable to read paper metadata.") from exc

    manuscript_needed = any(
        _uses_manuscript_references(
            marker,
            exclude_paper_id=exclude_paper_id,
            bib_paper_id=bib_paper_id,
        )
        for marker in markers
    )
    manuscript_references = None
    manuscript_error = None
    if manuscript_needed and exclude_paper_id:
        manuscript_references, manuscript_error = _load_reference_input(
            AuditRequest(manuscript_id=exclude_paper_id),
            lock_id=exclude_paper_id,
        )

    bibliography_needed = bool(bib_paper_id) or any(
        not _uses_manuscript_references(
            marker,
            exclude_paper_id=exclude_paper_id,
            bib_paper_id=bib_paper_id,
        )
        and not _NUMERIC_CITATION_RE.fullmatch(marker)
        for marker in markers
    )
    bibliography_references = None
    bibliography_entries = None
    bibliography_error = None
    if bibliography_needed:
        if bib_paper_id:
            bibliography_references, bibliography_error = _load_reference_input(
                AuditRequest(bib_paper_id=bib_paper_id),
                lock_id=bib_paper_id,
            )
        else:
            bibliography_entries = _load_bibliography_entries(records)

    source_catalog, skipped_source_count = _load_source_catalog(
        records,
        exclude_paper_id=exclude_paper_id,
    )
    return CitationLookupContext(
        records=records,
        exclude_paper_id=exclude_paper_id,
        bib_paper_id=bib_paper_id,
        manuscript_references=manuscript_references,
        manuscript_error=manuscript_error,
        bibliography_references=bibliography_references,
        bibliography_entries=bibliography_entries,
        bibliography_error=bibliography_error,
        source_catalog=source_catalog,
        skipped_source_count=skipped_source_count,
    )


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
    title = loaded.parsed.title or loaded.record.title or loaded.record.original_filename
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
    bib_paper_id: str | None = None,
    context: CitationLookupContext | None = None,
) -> CitationLookup:
    """Map a citation marker to a parsed source paper in the local library.

    Status precedence is fixed so the same marker always yields the same answer
    regardless of library contents: an unresolvable *marker form* is reported
    before a missing bibliography, which is reported before a missing reference.

    Args:
        marker: The citation marker exactly as extracted from the manuscript.
        exclude_paper_id: The manuscript owning numeric/author-year references;
            also excluded from the source catalog.
        bib_paper_id: Explicit bibliography for key/author-year markers. Numeric
            references always use their manuscript, never BibTeX entry order.
        context: Optional request-scoped inputs prepared by
            :func:`build_citation_lookup_context`. Supplying it avoids reloading
            the paper store, reference artifact and source catalog for each
            citation in a manuscript.

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

    if context is not None:
        if exclude_paper_id is None:
            exclude_paper_id = context.exclude_paper_id
        if bib_paper_id is None:
            bib_paper_id = context.bib_paper_id
        records = context.records
    else:
        try:
            records = list_papers()
        except PaperStoreError as exc:
            raise SourceLocatorError("Unable to read paper metadata.") from exc

    numeric = bool(_NUMERIC_CITATION_RE.fullmatch(clean_marker))
    lookup_marker = clean_marker
    reference_database = "Uploaded BibTeX"
    if numeric and not exclude_paper_id:
        return CitationLookup(
            marker=clean_marker,
            outcome=ComparisonStatus.MARKER_UNSUPPORTED,
            message="Numeric citations require their manuscript_id, not a BibTeX position.",
        )
    if numeric and not _is_single_numeric_marker(clean_marker):
        return CitationLookup(
            marker=clean_marker,
            outcome=ComparisonStatus.REFERENCE_AMBIGUOUS,
            message="Select one reference from this multi-reference marker before comparison.",
        )
    manuscript_references = _uses_manuscript_references(
        clean_marker,
        exclude_paper_id=exclude_paper_id,
        bib_paper_id=bib_paper_id,
    )
    if manuscript_references or bib_paper_id:
        if context is not None:
            if manuscript_references:
                references = context.manuscript_references
            elif bib_paper_id:
                references = context.bibliography_references
            else:
                references = context.bibliography_entries
            error = (
                context.manuscript_error if manuscript_references else context.bibliography_error
            )
            if error is not None:
                code, detail = error
                return CitationLookup(
                    marker=clean_marker,
                    outcome=ComparisonStatus.SOURCE_NOT_AVAILABLE,
                    message=f"Reference input unavailable ({code}): {detail}",
                )
        else:
            request = (
                AuditRequest(manuscript_id=exclude_paper_id)
                if manuscript_references
                else AuditRequest(bib_paper_id=bib_paper_id)
            )
            references, error = _load_reference_input(
                request,
                lock_id=exclude_paper_id if manuscript_references else bib_paper_id,
            )
            if error is not None:
                code, detail = error
                return CitationLookup(
                    marker=clean_marker,
                    outcome=ComparisonStatus.SOURCE_NOT_AVAILABLE,
                    message=f"Reference input unavailable ({code}): {detail}",
                )
        if manuscript_references or bib_paper_id:
            entries = [reference.metadata for reference in references or []]
        else:
            entries = references or []
        if manuscript_references:
            reference_database = "Manuscript reference list"
        if numeric:
            number = int(re.search(r"\d+", clean_marker).group())
            entries = [
                reference.metadata for reference in references or [] if reference.number == number
            ]
            lookup_marker = str(number)
            reference_database = "Manuscript reference list"
            if not entries:
                return CitationLookup(
                    marker=clean_marker,
                    outcome=ComparisonStatus.REFERENCE_NOT_FOUND,
                    message=f"Reference {number} is absent from this manuscript's reference list.",
                )
        else:
            entries = [reference.metadata for reference in references or []]
    elif context is not None:
        entries = context.bibliography_entries or []
    else:
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

    entry = _find_bib_entry(lookup_marker, entries)
    if entry is None:
        count = _candidate_count(lookup_marker, entries)
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

    if context is not None:
        catalog = context.source_catalog
        skipped = context.skipped_source_count
    else:
        catalog, skipped = _load_source_catalog(records, exclude_paper_id=exclude_paper_id)
    citation_key = entry.key or _fallback_key(clean_marker)
    source_pdf = _match_pdf_to_bib_entry(entry, catalog)
    cited_source = _source_from_bib(
        entry,
        citation_key,
        source_pdf.record.paper_id if source_pdf else None,
    )

    cited_source.database = reference_database

    if source_pdf is None:
        reason = f"No unique, compatible parsed PDF in the library matches '{citation_key}'."
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
