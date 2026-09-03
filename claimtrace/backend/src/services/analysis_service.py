"""Persisted claim extraction and citation-audit orchestration.

The service deliberately starts from the Parser output saved by the upload
pipeline.  It does not manufacture claims or source records: citation
markers come from the manuscript text, source metadata comes from uploaded
PDF/BibTeX records, and evidence comes from the parsed source paragraphs.

When an LLM client is configured, it classifies the best retrieved passage.
Local development and CI use the deterministic lexical analyser instead, so
the API remains useful without downloading an embedding model or calling an
external provider.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from ..models import (
    AuditResponse,
    CitationAuditResult,
    DocumentLocation,
    ExtractedClaim,
    IdentifiedSource,
    PaperClaimsResponse,
    PaperRecord,
    ParsedBibDocument,
    ParsedDocument,
    ParseStatus,
    SimilarSource,
    SourceDocument,
    SourceDocumentPage,
    SourceLocation,
    VerdictEnum,
)
from ..storage.bib_document_store import BibDocumentStoreError, load_bib_document
from ..storage.paper_store import PaperStoreError, get_paper, list_papers
from ..storage.parsed_document_store import (
    ParsedDocumentStoreError,
    load_parsed_document,
)


class AnalysisPaperNotFoundError(RuntimeError):
    """Raised when a requested paper ID is not in the paper store."""


class AnalysisPaperNotReadyError(RuntimeError):
    """Raised when parsing has not completed for a required PDF."""


class InvalidAnalysisPaperError(RuntimeError):
    """Raised when a paper has the wrong type or a failed parse state."""


class AnalysisServiceError(RuntimeError):
    """Raised when persisted analysis input cannot be loaded safely."""


_LATEX_CITATION_RE = re.compile(
    r"\\cite[a-zA-Z*]*(?:\s*\[[^\]]*\])?\s*\{[^{}]+\}"
)
_NUMERIC_CITATION_RE = re.compile(
    r"(?<!\w)(?:\[\s*\d+(?:\s*[-–—]\s*\d+)?"
    r"(?:\s*[,;]\s*\d+(?:\s*[-–—]\s*\d+)?)*\s*\]"
    r"|【\s*\d+(?:\s*[-–—]\s*\d+)?"
    r"(?:\s*[,;]\s*\d+(?:\s*[-–—]\s*\d+)?)*\s*】)"
)
_AUTHOR_YEAR_CITATION_RE = re.compile(
    r"\((?=[^()]{1,120}\b(?:19|20)\d{2}\b)(?=[^()]{1,120}[A-Za-z])[^()]{1,120}\)"
)
_SENTENCE_SPLIT_RE = re.compile(r"(?:(?<=[.!?])[\"')\]]*\s+|\s*\n+\s*)")
_YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")
_REFERENCE_HEADING_RE = re.compile(
    r"^(?:references?|bibliography|参考文献)\s*$", re.IGNORECASE
)
_NUMBERED_HEADING_RE = re.compile(r"^\d+(?:\.\d+)*[.)]?\s+\S")
_SECTION_HEADING_RE = re.compile(
    r"^(?:abstract|introduction|background|related work|method(?:ology)?|"
    r"experiments?|results?|discussion|conclusion|limitations?|appendix)\b",
    re.IGNORECASE,
)
_TOKEN_RE = re.compile(r"[\w][\w'’\-]*", re.UNICODE)
_STOP_WORDS = {
    "about",
    "after",
    "also",
    "and",
    "are",
    "been",
    "being",
    "between",
    "could",
    "from",
    "have",
    "into",
    "more",
    "over",
    "such",
    "than",
    "that",
    "their",
    "there",
    "these",
    "they",
    "this",
    "through",
    "using",
    "were",
    "which",
    "with",
}


@dataclass(frozen=True)
class _DocumentView:
    document: SourceDocument
    paragraph_locations: dict[int, DocumentLocation]


@dataclass(frozen=True)
class _LoadedPdf:
    record: PaperRecord
    parsed: ParsedDocument
    view: _DocumentView


@dataclass(frozen=True)
class _Passage:
    text: str
    source: _LoadedPdf
    location: DocumentLocation
    score: float


def _normalise_text(text: str) -> str:
    """Collapse PDF/Markdown whitespace without changing visible wording."""
    return re.sub(r"\s+", " ", text).strip()


def _tokens(text: str) -> set[str]:
    """Return informative case-folded tokens for local evidence ranking."""
    return {
        token.casefold()
        for token in _TOKEN_RE.findall(text)
        if len(token) > 2 and token.casefold() not in _STOP_WORDS
    }


def _similarity(claim: str, passage: str) -> float:
    """Measure how much of a claim is covered by a candidate passage."""
    claim_tokens = _tokens(claim)
    passage_tokens = _tokens(passage)
    if not claim_tokens or not passage_tokens:
        return 0.0
    return min(1.0, len(claim_tokens & passage_tokens) / len(claim_tokens))


def _split_sentences(text: str) -> list[str]:
    """Split a parsed paragraph while retaining complete evidence sentences."""
    normalised = _normalise_text(text)
    if not normalised:
        return []
    sentences = [_normalise_text(part) for part in _SENTENCE_SPLIT_RE.split(normalised)]
    return [sentence for sentence in sentences if sentence]


def _is_heading(text: str) -> bool:
    """Use conservative heuristics for page headings in the display contract."""
    normalised = _normalise_text(text)
    if not normalised or len(normalised) > 140:
        return False
    return bool(
        _REFERENCE_HEADING_RE.fullmatch(normalised)
        or _NUMBERED_HEADING_RE.match(normalised)
        or _SECTION_HEADING_RE.match(normalised)
    )


def _build_document_view(document: ParsedDocument) -> _DocumentView:
    """Group persisted paragraphs into pages and retain display locations."""
    total_pages = max(document.pages, 1)
    pages = [
        SourceDocumentPage(page=page, heading=None, paragraphs=[])
        for page in range(1, total_pages + 1)
    ]
    locations: dict[int, DocumentLocation] = {}

    for paragraph_index, paragraph in enumerate(document.paragraphs):
        text = _normalise_text(paragraph.text)
        if not text:
            continue
        page_number = min(max(paragraph.page_start, 1), total_pages)
        page = pages[page_number - 1]
        if _is_heading(text) and page.heading is None:
            page.heading = text
            continue

        display_index = len(page.paragraphs)
        page.paragraphs.append(text)
        locations[paragraph_index] = DocumentLocation(
            page=page_number,
            paragraph_index=display_index,
        )

    return _DocumentView(
        document=SourceDocument(total_pages=total_pages, pages=pages, matched_location=None),
        paragraph_locations=locations,
    )


def _citation_markers(text: str) -> list[str]:
    """Extract LaTeX, numeric, and author-year citation markers in order."""
    matches = [
        *(_LATEX_CITATION_RE.finditer(text)),
        *(_NUMERIC_CITATION_RE.finditer(text)),
        *(_AUTHOR_YEAR_CITATION_RE.finditer(text)),
    ]
    markers: list[str] = []
    seen: set[tuple[int, int]] = set()
    for match in sorted(matches, key=lambda item: (item.start(), item.end())):
        span = (match.start(), match.end())
        if span in seen:
            continue
        seen.add(span)
        marker = _normalise_text(match.group(0))
        if marker and marker not in markers:
            markers.append(marker)
    return markers


def _citation_keys(marker: str) -> list[str]:
    """Return direct BibTeX keys or numeric references represented by a marker."""
    latex_match = re.search(r"\{([^{}]+)\}", marker)
    if latex_match:
        return [key.strip() for key in latex_match.group(1).split(",") if key.strip()]
    numbers = re.findall(r"\d+", marker)
    return numbers[:1]


def _first_author_surname(authors: Iterable[str]) -> str:
    """Extract a conservative surname token from BibTeX author text."""
    first = next(iter(authors), "")
    surname = first.split(",", 1)[0] if "," in first else first.split()[0] if first else ""
    return re.sub(r"[^\w'-]", "", surname).casefold()


def _find_bib_entry(marker: str, entries: list[Any]) -> Any | None:
    """Resolve a marker against persisted BibTeX entries when possible."""
    clean_marker = marker.strip("()[]【】 ")
    keys = {key.casefold() for key in _citation_keys(marker)}
    if clean_marker:
        keys.add(clean_marker.casefold())
    for entry in entries:
        if entry.key.casefold() in keys:
            return entry

    numbers = re.findall(r"\d+", marker)
    if numbers and not _LATEX_CITATION_RE.fullmatch(marker):
        index = int(numbers[0]) - 1
        if 0 <= index < len(entries):
            return entries[index]

    year_match = _YEAR_RE.search(marker)
    if year_match:
        year = int(year_match.group(0))
        marker_tokens = _tokens(marker)
        for entry in entries:
            surname = _first_author_surname(entry.authors)
            if entry.year == year and surname and surname in marker_tokens:
                return entry
    return None


def _load_bibliography_entries(records: list[PaperRecord]) -> list[Any]:
    """Read completed BibTeX entries for citation-key resolution."""
    entries: list[Any] = []
    for record in records:
        if (
            record.file_type != "bib"
            or record.status != ParseStatus.COMPLETED
            or not record.parsed_result_path
        ):
            continue
        try:
            document: ParsedBibDocument = load_bib_document(Path(record.parsed_result_path))
        except BibDocumentStoreError:
            # An unrelated broken bibliography must not hide manuscript claims.
            continue
        entries.extend(document.entries)
    return entries


def _title_similarity(left: str, right: str) -> float:
    """Score two titles using token coverage, with exact titles scoring one."""
    left_tokens = _tokens(left)
    right_tokens = _tokens(right)
    if not left_tokens or not right_tokens:
        return 0.0
    if left.casefold() == right.casefold():
        return 1.0
    overlap = len(left_tokens & right_tokens)
    return overlap / max(len(left_tokens), len(right_tokens))


def _load_completed_pdf(record: PaperRecord) -> _LoadedPdf:
    """Load and validate one completed parsed PDF."""
    if not record.parsed_result_path:
        raise AnalysisServiceError("Parsed paper output is missing.")
    try:
        parsed = load_parsed_document(Path(record.parsed_result_path))
    except ParsedDocumentStoreError as exc:
        raise AnalysisServiceError("Unable to read parsed paper output.") from exc
    if parsed.paper_id != record.paper_id:
        raise AnalysisServiceError("Parsed paper ID does not match the request.")
    return _LoadedPdf(record=record, parsed=parsed, view=_build_document_view(parsed))


def _load_completed_pdf_catalog(
    records: list[PaperRecord],
    *,
    exclude_paper_id: str | None = None,
) -> list[_LoadedPdf]:
    """Load all usable source PDFs from persisted paper records."""
    catalog: list[_LoadedPdf] = []
    for record in records:
        if (
            record.file_type != "pdf"
            or record.paper_id == exclude_paper_id
            or record.status != ParseStatus.COMPLETED
            or not record.parsed_result_path
        ):
            continue
        catalog.append(_load_completed_pdf(record))
    return catalog


def _source_from_pdf(source: _LoadedPdf, citation_key: str) -> IdentifiedSource:
    """Adapt persisted PDF metadata to the frontend source contract."""
    title = source.parsed.title or source.record.title or Path(
        source.record.original_filename
    ).stem
    return IdentifiedSource(
        source_paper_id=source.record.paper_id,
        citation_key=citation_key,
        title=title,
        authors=list(source.parsed.authors),
        venue=source.parsed.venue,
        year=source.parsed.year,
        doi=source.parsed.doi,
        url=None,
        database="ClaimTrace Paper Library",
    )


def _source_from_bib(entry: Any, citation_key: str, source_id: str | None) -> IdentifiedSource:
    """Adapt a persisted BibTeX entry to the frontend source contract."""
    return IdentifiedSource(
        source_paper_id=source_id,
        citation_key=entry.key or citation_key,
        title=entry.title or entry.key or citation_key,
        authors=list(entry.authors),
        venue=entry.venue or None,
        year=entry.year,
        doi=entry.doi or None,
        url=entry.url or None,
        database="Uploaded BibTeX",
    )


def _match_pdf_to_bib_entry(entry: Any, pdfs: list[_LoadedPdf]) -> _LoadedPdf | None:
    """Find a local PDF whose persisted metadata matches a BibTeX entry."""
    best: tuple[float, _LoadedPdf | None] = (0.0, None)
    entry_doi = (entry.doi or "").casefold().strip()
    for source in pdfs:
        if entry_doi and source.parsed.doi and entry_doi == source.parsed.doi.casefold().strip():
            return source
        score = _title_similarity(entry.title, source.parsed.title or source.record.title or "")
        if entry.year is not None and source.parsed.year == entry.year:
            score += 0.1
        score = min(score, 1.0)
        if score > best[0]:
            best = (score, source)
    return best[1] if best[0] >= 0.65 else None


def _resolve_bib_source(
    marker: str,
    entries: list[Any],
    pdfs: list[_LoadedPdf],
) -> tuple[IdentifiedSource | None, _LoadedPdf | None]:
    """Resolve a claim's marker to BibTeX metadata and an optional local PDF."""
    entry = _find_bib_entry(marker, entries)
    if entry is None:
        return None, None
    source_pdf = _match_pdf_to_bib_entry(entry, pdfs)
    source = _source_from_bib(entry, marker, source_pdf.record.paper_id if source_pdf else None)
    return source, source_pdf


def _claim_id(
    manuscript_id: str,
    page: int | None,
    paragraph_index: int,
    sentence_index: int,
    marker: str,
    text: str,
) -> str:
    """Create a stable ID for one citation occurrence."""
    raw = "|".join(
        [manuscript_id, str(page or 0), str(paragraph_index), str(sentence_index), marker, text]
    )
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
    return f"claim-{digest}"


def extract_claims(
    document: ParsedDocument,
    *,
    manuscript_id: str,
    bibliography_entries: list[Any] | None = None,
    source_pdfs: list[_LoadedPdf] | None = None,
) -> tuple[list[ExtractedClaim], _DocumentView]:
    """Extract citation-bearing manuscript sentences from a ParsedDocument."""
    entries = bibliography_entries or []
    pdfs = source_pdfs or []
    view = _build_document_view(document)
    claims: list[ExtractedClaim] = []
    in_references = False

    for paragraph_index, paragraph in enumerate(document.paragraphs):
        paragraph_text = _normalise_text(paragraph.text)
        if not paragraph_text:
            continue
        if _REFERENCE_HEADING_RE.fullmatch(paragraph_text):
            in_references = True
            continue
        if in_references:
            continue

        location = view.paragraph_locations.get(paragraph_index)
        if location is None:
            continue
        for sentence_index, sentence in enumerate(_split_sentences(paragraph_text)):
            markers = _citation_markers(sentence)
            if not markers or len(_tokens(sentence)) < 3:
                continue
            for marker in markers:
                source, source_pdf = _resolve_bib_source(marker, entries, pdfs)
                source_document = source_pdf.view.document if source_pdf else None
                claims.append(
                    ExtractedClaim(
                        claim_id=_claim_id(
                            manuscript_id,
                            location.page,
                            paragraph_index,
                            sentence_index,
                            marker,
                            sentence,
                        ),
                        text=sentence,
                        page=location.page,
                        citation_marker=marker,
                        resolution_status="identified" if source else "not_found",
                        cited_source=source,
                        similar_sources=[],
                        source_document=source_document,
                        manuscript_location=location,
                    )
                )
    return claims, view


def get_paper_claims(paper_id: str) -> PaperClaimsResponse:
    """Return real claims and manuscript text from persisted Parser output."""
    try:
        record = get_paper(paper_id)
    except PaperStoreError as exc:
        raise AnalysisServiceError("Unable to read paper metadata.") from exc

    if record is None:
        raise AnalysisPaperNotFoundError("Paper not found.")
    if record.file_type != "pdf":
        raise InvalidAnalysisPaperError("Only parsed PDF files have manuscript claims.")
    if record.status in {ParseStatus.PENDING, ParseStatus.PROCESSING}:
        return PaperClaimsResponse(
            manuscript_id=paper_id,
            status=record.status,
            claims=[],
            error_message="Paper parsing has not completed.",
        )
    if record.status == ParseStatus.FAILED:
        return PaperClaimsResponse(
            manuscript_id=paper_id,
            status=record.status,
            claims=[],
            error_message=record.error_message or "Paper parsing failed.",
        )

    parsed = _load_completed_pdf(record)
    try:
        records = list_papers()
    except PaperStoreError as exc:
        raise AnalysisServiceError("Unable to read paper metadata.") from exc
    entries = _load_bibliography_entries(records)
    source_pdfs = _load_completed_pdf_catalog(records, exclude_paper_id=paper_id)
    claims, view = extract_claims(
        parsed.parsed,
        manuscript_id=paper_id,
        bibliography_entries=entries,
        source_pdfs=source_pdfs,
    )
    return PaperClaimsResponse(
        manuscript_id=paper_id,
        status=ParseStatus.COMPLETED,
        claims=claims,
        error_message=None,
        manuscript_document=view.document,
    )


def _passages_for_source(claim: str, source: _LoadedPdf) -> list[_Passage]:
    """Create sentence-level evidence candidates for one source PDF."""
    passages: list[_Passage] = []
    for paragraph_index, paragraph in enumerate(source.parsed.paragraphs):
        location = source.view.paragraph_locations.get(paragraph_index)
        if location is None:
            continue
        sentences = _split_sentences(paragraph.text) or [_normalise_text(paragraph.text)]
        for sentence in sentences:
            if not sentence:
                continue
            passages.append(
                _Passage(
                    text=sentence,
                    source=source,
                    location=location,
                    score=round(_similarity(claim, sentence), 4),
                )
            )
    return sorted(
        passages,
        key=lambda passage: (-passage.score, passage.source.record.paper_id, passage.location.page),
    )


def _rank_passages(claim: str, sources: list[_LoadedPdf]) -> list[_Passage]:
    """Rank evidence across the source PDFs supplied to the audit request."""
    passages = [
        passage
        for source in sources
        for passage in _passages_for_source(claim, source)
    ]
    return sorted(
        passages,
        key=lambda passage: (
            -passage.score,
            passage.source.record.paper_id,
            passage.location.page,
            passage.location.paragraph_index,
        ),
    )


def _llm_classification(
    claim: str,
    passage: str,
    *,
    client: Any | None,
    model: str,
) -> tuple[VerdictEnum, float, str] | None:
    """Ask a configured OpenAI-compatible client for entailment classification."""
    if client is None:
        return None
    prompt = f"""You are a citation verification assistant for academic papers.
Determine whether the source passage supports the manuscript claim.

SOURCE PASSAGE:
\"\"\"
{passage}
\"\"\"

MANUSCRIPT CLAIM:
\"\"\"
{claim}
\"\"\"

Return JSON only with this shape:
{{\"label\": \"SUPPORT\" | \"PARTIAL\" | \"CONTRADICT\" | \"NOT_FOUND\", "
        "\"rationale\": \"brief explanation grounded in the passage\"}}"""
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content
        parsed = json.loads(content)
        verdict = VerdictEnum(str(parsed.get("label", "NOT_FOUND")).upper())
        rationale = str(parsed.get("rationale", "No rationale was returned.")).strip()
        confidence = 0.85 if verdict in {VerdictEnum.SUPPORT, VerdictEnum.PARTIAL} else 0.3
        return verdict, confidence, rationale or "No rationale was returned."
    except Exception:
        # The persisted local evidence result is still useful if a provider is
        # unavailable or returns malformed data.  Do not turn an audit into a
        # 500 just because optional LLM enrichment failed.
        return None


def _local_classification(claim: str, passage: _Passage | None) -> tuple[VerdictEnum, float, str]:
    """Classify evidence deterministically when no LLM is available."""
    if passage is None or passage.score < 0.2:
        score = passage.score if passage else 0.0
        confidence = round(0.2 + score * 0.15, 4)
        return (
            VerdictEnum.NOT_FOUND,
            confidence,
            "No sufficiently similar passage was found in the uploaded source PDFs.",
        )
    if passage.score >= 0.65:
        confidence = round(min(0.95, 0.55 + passage.score * 0.4), 4)
        return (
            VerdictEnum.SUPPORT,
            confidence,
            "The highest-overlap passage in the uploaded source PDFs supports the claim.",
        )
    confidence = round(min(0.85, 0.45 + passage.score * 0.35), 4)
    return (
        VerdictEnum.PARTIAL,
        confidence,
        "The uploaded source PDFs contain overlapping evidence, but the match is incomplete.",
    )


def _risk_level(verdict: VerdictEnum) -> str:
    """Map a verdict to the review risk shown by the frontend."""
    if verdict == VerdictEnum.SUPPORT:
        return "low"
    if verdict == VerdictEnum.PARTIAL:
        return "medium"
    return "high"


def _similar_source_candidates(
    marker: str,
    ranked: list[_Passage],
    *,
    chosen: _LoadedPdf | None,
) -> list[SimilarSource]:
    """Return distinct alternative PDFs for unresolved citations."""
    candidates: list[SimilarSource] = []
    seen: set[str] = set()
    for passage in ranked:
        paper_id = passage.source.record.paper_id
        if paper_id in seen or passage.source is chosen or passage.score <= 0:
            continue
        seen.add(paper_id)
        source = _source_from_pdf(passage.source, marker)
        candidates.append(SimilarSource(**source.model_dump(), similarity=passage.score))
        if len(candidates) == 3:
            break
    return candidates


def run_audit(
    manuscript_id: str,
    source_paper_ids: list[str],
    *,
    llm_client: Any | None = None,
    llm_model: str = "",
) -> AuditResponse:
    """Extract manuscript claims and compare each with uploaded source PDFs."""
    try:
        manuscript_record = get_paper(manuscript_id)
    except PaperStoreError as exc:
        raise AnalysisServiceError("Unable to read paper metadata.") from exc
    if manuscript_record is None:
        raise AnalysisPaperNotFoundError("Manuscript not found.")
    if manuscript_record.file_type != "pdf":
        raise InvalidAnalysisPaperError("Only a PDF manuscript can be audited.")
    if manuscript_record.status in {ParseStatus.PENDING, ParseStatus.PROCESSING}:
        raise AnalysisPaperNotReadyError("Manuscript parsing has not completed.")
    if manuscript_record.status == ParseStatus.FAILED:
        raise InvalidAnalysisPaperError(
            manuscript_record.error_message or "Manuscript parsing failed."
        )

    source_ids = list(dict.fromkeys(source_paper_ids))
    sources: list[_LoadedPdf] = []
    for source_id in source_ids:
        try:
            record = get_paper(source_id)
        except PaperStoreError as exc:
            raise AnalysisServiceError("Unable to read source paper metadata.") from exc
        if record is None:
            raise AnalysisPaperNotFoundError(f"Source paper not found: {source_id}.")
        if record.file_type != "pdf":
            raise InvalidAnalysisPaperError(f"Source paper is not a PDF: {source_id}.")
        if record.status in {ParseStatus.PENDING, ParseStatus.PROCESSING}:
            raise AnalysisPaperNotReadyError(
                f"Source paper parsing has not completed: {source_id}."
            )
        if record.status == ParseStatus.FAILED:
            raise InvalidAnalysisPaperError(
                record.error_message or f"Source paper parsing failed: {source_id}."
            )
        sources.append(_load_completed_pdf(record))

    manuscript = _load_completed_pdf(manuscript_record)
    try:
        records = list_papers()
    except PaperStoreError as exc:
        raise AnalysisServiceError("Unable to read paper metadata.") from exc
    entries = _load_bibliography_entries(records)
    claims, manuscript_view = extract_claims(
        manuscript.parsed,
        manuscript_id=manuscript_id,
        bibliography_entries=entries,
        source_pdfs=sources,
    )

    results: list[CitationAuditResult] = []
    for claim in claims:
        resolved_id = claim.cited_source.source_paper_id if claim.cited_source else None
        allowed_sources = [source for source in sources if source.record.paper_id == resolved_id]
        if not allowed_sources:
            allowed_sources = sources

        ranked = _rank_passages(claim.text, allowed_sources)
        best = ranked[0] if ranked else None
        local_verdict, local_confidence, local_rationale = _local_classification(claim.text, best)
        llm_result = _llm_classification(
            claim.text,
            best.text if best and best.score >= 0.2 else "",
            client=llm_client,
            model=llm_model,
        ) if best and best.score >= 0.2 else None
        verdict, confidence, rationale = llm_result or (
            local_verdict,
            local_confidence,
            local_rationale,
        )

        selected_source = best.source if best else None
        cited_source = (
            claim.cited_source
            if resolved_id and selected_source and selected_source.record.paper_id == resolved_id
            else _source_from_pdf(selected_source, claim.citation_marker)
            if selected_source
            else claim.cited_source
        )
        source_document = None
        source_location = None
        source_passage = None
        if best:
            source_passage = best.text
            source_document = best.source.view.document.model_copy(
                update={"matched_location": best.location}
            )
            source_location = SourceLocation(
                page=best.location.page,
                quote=best.text,
                annotation=(
                    "Matched source passage"
                    if verdict == VerdictEnum.SUPPORT
                    else "Evidence partially overlaps the claim"
                    if verdict == VerdictEnum.PARTIAL
                    else "Source analysis found a high-risk result"
                ),
            )
        if resolved_id and not any(source.record.paper_id == resolved_id for source in sources):
            rationale = (
                "The BibTeX record was identified, but its uploaded source PDF was not "
                "included in this audit request."
            )
            verdict = VerdictEnum.NOT_FOUND
            confidence = 0.2
            cited_source = claim.cited_source
            source_document = None
            source_location = None
            source_passage = None

        results.append(
            CitationAuditResult(
                citation_key=claim.cited_source.citation_key
                if claim.cited_source
                else claim.citation_marker,
                claim=claim.text,
                verdict=verdict,
                confidence=round(confidence, 4),
                risk_level=_risk_level(verdict),
                claim_id=claim.claim_id,
                manuscript_location=claim.manuscript_location,
                source_location=source_location,
                cited_source=cited_source,
                source_passage=source_passage,
                source_document=source_document,
                comparison_rationale=rationale,
                similar_sources=_similar_source_candidates(
                    claim.citation_marker,
                    ranked,
                    chosen=selected_source,
                ) if not claim.cited_source else [],
            )
        )

    return AuditResponse(
        manuscript_id=manuscript_id,
        total_citations=len(results),
        supported=sum(result.verdict == VerdictEnum.SUPPORT for result in results),
        partial=sum(result.verdict == VerdictEnum.PARTIAL for result in results),
        contradicted=sum(result.verdict == VerdictEnum.CONTRADICT for result in results),
        not_found=sum(result.verdict == VerdictEnum.NOT_FOUND for result in results),
        results=results,
        manuscript_document=manuscript_view.document,
    )
