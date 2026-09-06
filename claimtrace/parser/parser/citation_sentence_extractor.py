"""Extract sentences containing numbered in-text citations.

This module handles square-bracket citation styles such as ``[1]``,
``[1][15]``, ``[3, 4]``, and ``[5-7]``.  It deliberately operates on
OpenDataLoader document elements instead of raw page text so that PDF layout
artifacts (columns, tables, equations, headers, and footers) can be filtered
before sentence extraction.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf

from .opendataloader_adapter import ConvertedDocument, DocumentElement, convert_pdf
from .reference_json_extractor import (
    ReferenceList,
    collect_reference_elements,
    extract_references_from_document,
    find_reference_section,
    order_reference_elements,
)

BRACKET_CITATION_PATTERN = re.compile(
    r"\[(?P<numbers>\d+(?:\s*(?:,|[-\u2013\u2014])\s*\d+)*)\]"
)
_RANGE_SEPARATOR_PATTERN = re.compile(r"\s*[-\u2013\u2014]\s*")
_WORD_PATTERN = re.compile(r"[^\W\d_]+", flags=re.UNICODE)
_LINE_BREAK_HYPHEN_PATTERN = re.compile(r"(?<=\w)-\s*\n\s*(?=[a-z])")

_EXCLUDED_ELEMENT_TYPES = {
    "caption",
    "equation",
    "figure",
    "footer",
    "formula",
    "header",
    "heading",
    "page number",
    "page-number",
    "table",
    "title",
}

_PERIOD_ABBREVIATIONS = (
    "cf.",
    "dr.",
    "e.g.",
    "eq.",
    "eqs.",
    "et al.",
    "etc.",
    "fig.",
    "figs.",
    "i.e.",
    "mr.",
    "mrs.",
    "ms.",
    "no.",
    "pp.",
    "prof.",
    "ref.",
    "refs.",
    "sec.",
    "st.",
    "v.",
    "vol.",
    "vs.",
)


@dataclass
class CitationMarker:
    """One citation marker and its position inside a normalized sentence."""

    text: str
    reference_ids: tuple[int, ...]
    start: int
    end: int
    locations: list[CitationLocation] = field(default_factory=list)


@dataclass(frozen=True)
class CitationLocation:
    """PDF coordinates that locate a square-bracket citation marker."""

    page: int
    bounding_boxes: tuple[tuple[float, float, float, float], ...]


@dataclass
class CitedSentence:
    """One sentence containing at least one validated citation marker."""

    sentence_id: str
    text: str
    markers: list[CitationMarker] = field(default_factory=list)
    page_start: int | None = None
    page_end: int | None = None
    source_element_ids: list[str] = field(default_factory=list)

    @property
    def citation_ids(self) -> list[int]:
        """Return cited reference numbers in first-occurrence order."""

        seen: set[int] = set()
        ordered: list[int] = []
        for marker in self.markers:
            for reference_id in marker.reference_ids:
                if reference_id not in seen:
                    seen.add(reference_id)
                    ordered.append(reference_id)
        return ordered


@dataclass
class CitationSentenceList:
    """All citation-bearing sentences extracted from one document."""

    source_file: str = ""
    sentences: list[CitedSentence] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class _TextRun:
    """One paragraph-like text run, possibly continued across elements."""

    order: int
    text: str
    page_start: int
    page_end: int
    source_element_ids: list[str]


def _normalize_text(text: str) -> str:
    """Repair line-wrap hyphenation and collapse PDF extraction whitespace."""

    text = _LINE_BREAK_HYPHEN_PATTERN.sub("", text)
    return " ".join(text.split()).strip()


def _is_protected_period(text: str, index: int) -> bool:
    """Return whether a period belongs to a decimal, version, or abbreviation."""

    previous = text[index - 1] if index else ""
    following = text[index + 1] if index + 1 < len(text) else ""
    if previous.isdigit() and following.isdigit():
        return True

    prefix = text[: index + 1].lower()
    if prefix.endswith(_PERIOD_ABBREVIATIONS):
        return True

    # Protect initials and acronyms such as ``J. Smith`` and ``U.S.``.
    if re.search(r"(?:\b[A-Za-z]\.){1,}$", text[: index + 1]):
        return True

    # A dot surrounded by non-whitespace is normally part of a URL, DOI,
    # e-mail address, or filename rather than a sentence boundary.
    return bool(previous and following and not previous.isspace() and not following.isspace())


def _sentence_spans(text: str) -> list[tuple[int, int]]:
    """Split normalized text into sentence spans with conservative rules."""

    spans: list[tuple[int, int]] = []
    start = 0
    index = 0

    while index < len(text):
        character = text[index]
        is_boundary = character in "?!" or (
            character == "." and not _is_protected_period(text, index)
        )
        if not is_boundary:
            index += 1
            continue

        end = index + 1
        while end < len(text) and text[end] in ".?!\"'\u2019\u201d)]}":
            end += 1

        if end == len(text) or text[end].isspace():
            if text[start:end].strip():
                spans.append((start, end))
            start = end
            while start < len(text) and text[start].isspace():
                start += 1
            index = start
            continue

        index += 1

    if text[start:].strip():
        spans.append((start, len(text)))

    return spans


def _expand_reference_ids(numbers: str, maximum_range_size: int = 100) -> tuple[int, ...]:
    """Expand comma-separated reference numbers and bounded numeric ranges."""

    expanded: list[int] = []
    for part in numbers.split(","):
        part = part.strip()
        range_parts = _RANGE_SEPARATOR_PATTERN.split(part)
        if len(range_parts) == 1:
            expanded.append(int(part))
            continue

        if len(range_parts) != 2:
            return ()

        start, end = (int(value) for value in range_parts)
        if end < start or end - start + 1 > maximum_range_size:
            return ()
        expanded.extend(range(start, end + 1))

    return tuple(expanded)


def _valid_markers(
    sentence: str,
    valid_reference_ids: set[int],
) -> list[CitationMarker]:
    """Find markers whose every number exists in the reference list."""

    markers: list[CitationMarker] = []
    for match in BRACKET_CITATION_PATTERN.finditer(sentence):
        reference_ids = _expand_reference_ids(match.group("numbers"))
        if not reference_ids or not set(reference_ids).issubset(valid_reference_ids):
            continue
        markers.append(
            CitationMarker(
                text=match.group(0),
                reference_ids=reference_ids,
                start=match.start(),
                end=match.end(),
            )
        )
    return markers


def _looks_like_prose(sentence: str) -> bool:
    """Reject short mathematical fragments that happen to contain brackets."""

    without_markers = BRACKET_CITATION_PATTERN.sub(" ", sentence)
    return len(_WORD_PATTERN.findall(without_markers)) >= 4


def _body_elements(document: ConvertedDocument) -> list[DocumentElement]:
    """Return elements before the logical reference-list region."""

    section = find_reference_section(document)
    if section is None:
        return []

    reference_element_ids = {
        id(element) for element in collect_reference_elements(document, section)
    }
    elements = [
        element
        for element in document.elements[: section.heading_index]
        if id(element) not in reference_element_ids
    ]
    return order_reference_elements(elements)


def _common_paragraph_left_edges(elements: list[DocumentElement]) -> list[float]:
    """Infer up to two main text-column left edges from paragraph geometry."""

    counts: dict[int, int] = {}
    for element in elements:
        if element.element_type.strip().lower() != "paragraph" or element.bbox is None:
            continue
        bucket = round(element.bbox[0] / 10)
        counts[bucket] = counts.get(bucket, 0) + 1

    if not counts:
        return []

    left = min(counts)
    right_candidates = [bucket for bucket in counts if bucket >= left + 10]
    edges = [left]
    if right_candidates:
        right = max(right_candidates, key=lambda bucket: (counts[bucket], bucket))
        edges.append(right)
    return [bucket * 10.0 for bucket in edges]


def _is_column_paragraph(
    element: DocumentElement,
    column_left_edges: list[float],
) -> bool:
    """Return whether an element resembles a main-column paragraph."""

    if element.element_type.strip().lower() != "paragraph":
        return False
    if element.bbox is None or not column_left_edges:
        return True
    if len(column_left_edges) > 1:
        column_width = column_left_edges[1] - column_left_edges[0]
        if element.bbox[2] - element.bbox[0] > column_width + 40.0:
            return False
    return any(abs(element.bbox[0] - edge) <= 18.0 for edge in column_left_edges)


def _starts_like_continuation(text: str) -> bool:
    """Recognize a lower-case continuation after a PDF element boundary."""

    match = re.search(r"[^\W\d_]", text, flags=re.UNICODE)
    return bool(match and match.group(0).islower())


def _ends_with_sentence_boundary(text: str) -> bool:
    """Return whether normalized text ends with sentence punctuation."""

    return bool(re.search(r"[.!?][\"'\u2019\u201d)\]}]*$", text.rstrip()))


def _text_runs(elements: list[DocumentElement]) -> list[_TextRun]:
    """Build text runs while recovering obvious cross-element continuations."""

    column_left_edges = _common_paragraph_left_edges(elements)
    standalone: list[_TextRun] = []
    column_elements: list[tuple[int, DocumentElement]] = []

    for order, element in enumerate(elements):
        if element.element_type.strip().lower() in _EXCLUDED_ELEMENT_TYPES:
            continue
        normalized = _normalize_text(element.content)
        if not normalized:
            continue

        if _is_column_paragraph(element, column_left_edges):
            column_elements.append((order, element))
        else:
            standalone.append(
                _TextRun(
                    order=order,
                    text=normalized,
                    page_start=element.page,
                    page_end=element.page,
                    source_element_ids=[element.element_id],
                )
            )

    merged: list[_TextRun] = []
    current: _TextRun | None = None
    for order, element in column_elements:
        normalized = _normalize_text(element.content)
        can_continue = bool(
            current
            and element.page <= current.page_end + 1
            and not _ends_with_sentence_boundary(current.text)
            and _starts_like_continuation(normalized)
        )

        if can_continue and current is not None:
            current.text = f"{current.text} {normalized}"
            current.page_end = element.page
            current.source_element_ids.append(element.element_id)
            continue

        if current is not None:
            merged.append(current)
        current = _TextRun(
            order=order,
            text=normalized,
            page_start=element.page,
            page_end=element.page,
            source_element_ids=[element.element_id],
        )

    if current is not None:
        merged.append(current)

    return sorted([*standalone, *merged], key=lambda run: run.order)


def extract_citation_sentences_from_document(
    document: ConvertedDocument,
    reference_list: ReferenceList | None = None,
) -> CitationSentenceList:
    """Extract complete sentences containing validated numbered citations."""

    resolved_references = reference_list or extract_references_from_document(document)
    valid_reference_ids = {
        reference.number
        for reference in resolved_references.references
        if reference.number is not None
    }
    warnings: list[str] = []

    if not valid_reference_ids:
        warnings.append(
            "No numbered reference list was found; bracketed citation extraction was skipped."
        )
        return CitationSentenceList(source_file=document.file_name, warnings=warnings)

    elements = _body_elements(document)
    if not elements:
        warnings.append(
            "Reference-list boundary was not found; citation extraction was skipped."
        )
        return CitationSentenceList(source_file=document.file_name, warnings=warnings)

    sentences: list[CitedSentence] = []
    for run in _text_runs(elements):
        for start, end in _sentence_spans(run.text):
            sentence = run.text[start:end].strip()
            markers = _valid_markers(sentence, valid_reference_ids)
            if not markers or not _looks_like_prose(sentence):
                continue

            sentence_number = len(sentences) + 1
            sentences.append(
                CitedSentence(
                    sentence_id=f"citation-sentence-{sentence_number:04d}",
                    text=sentence,
                    markers=markers,
                    page_start=run.page_start or None,
                    page_end=run.page_end or None,
                    source_element_ids=run.source_element_ids,
                )
            )

    return CitationSentenceList(
        source_file=document.file_name,
        sentences=sentences,
        warnings=warnings,
    )


def _opendataloader_bbox_to_pymupdf(
    bbox: tuple[float, float, float, float],
    page_height: float,
) -> pymupdf.Rect:
    """Convert bottom-left OpenDataLoader coordinates to top-left PDF coordinates."""

    x0, y0, x1, y1 = bbox
    return pymupdf.Rect(x0, page_height - y1, x1, page_height - y0)


def _locations_from_rectangles(
    rectangles_by_page: dict[int, list[pymupdf.Rect]],
) -> list[CitationLocation]:
    """Create ordered locations from page-indexed PDF rectangles."""

    return [
        CitationLocation(
            page=page_number,
            bounding_boxes=tuple(
                tuple(round(value, 3) for value in rectangle)
                for rectangle in rectangles
            ),
        )
        for page_number, rectangles in sorted(rectangles_by_page.items())
        if rectangles
    ]


def locate_citation_markers(
    pdf_path: Path,
    document: ConvertedDocument,
    result: CitationSentenceList,
) -> CitationSentenceList:
    """Attach the PDF position of each square-bracket citation marker."""

    elements_by_id = {element.element_id: element for element in document.elements}
    used_occurrences: dict[tuple[tuple[str, ...], str], int] = {}

    with pymupdf.open(Path(pdf_path)) as pdf:
        for sentence in result.sentences:
            page_start = max(1, sentence.page_start or 1)
            page_end = min(len(pdf), sentence.page_end or page_start)
            for marker in sentence.markers:
                candidates: list[tuple[int, pymupdf.Rect]] = []
                for element_id in sentence.source_element_ids:
                    element = elements_by_id.get(element_id)
                    if element is None or element.bbox is None:
                        continue
                    if not 1 <= element.page <= len(pdf):
                        continue

                    page = pdf[element.page - 1]
                    clip = _opendataloader_bbox_to_pymupdf(
                        element.bbox,
                        page.rect.height,
                    )
                    candidates.extend(
                        (element.page, match)
                        for match in page.search_for(marker.text, clip=clip)
                    )

                if not candidates:
                    for page_number in range(page_start, page_end + 1):
                        candidates.extend(
                            (page_number, match)
                            for match in pdf[page_number - 1].search_for(marker.text)
                        )

                candidates.sort(key=lambda item: (item[0], item[1].y0, item[1].x0))
                occurrence_key = (tuple(sentence.source_element_ids), marker.text)
                occurrence_index = used_occurrences.get(occurrence_key, 0)
                if occurrence_index >= len(candidates):
                    continue

                page_number, rectangle = candidates[occurrence_index]
                used_occurrences[occurrence_key] = occurrence_index + 1
                marker.locations = _locations_from_rectangles(
                    {page_number: [rectangle]},
                )

    return result


def extract_citation_sentences(pdf_path: Path) -> CitationSentenceList:
    """Convert a PDF once, then extract its reference-linked sentences."""

    pdf_path = Path(pdf_path)
    document = convert_pdf(pdf_path)
    references = extract_references_from_document(document)
    result = extract_citation_sentences_from_document(document, references)
    return locate_citation_markers(pdf_path, document, result)


def citation_sentence_list_to_dict(result: CitationSentenceList) -> dict:
    """Return one public JSON record per citation-to-reference link."""

    citations: list[dict] = []
    for sentence in result.sentences:
        for marker in sentence.markers:
            for reference_id in marker.reference_ids:
                citations.append(
                    {
                        "citation_id": reference_id,
                        "marker": marker.text,
                        "sentence_id": sentence.sentence_id,
                        "sentence": sentence.text,
                        "locations": [
                            {
                                "page": location.page,
                                "bounding_boxes": [
                                    {
                                        "x0": bbox[0],
                                        "y0": bbox[1],
                                        "x1": bbox[2],
                                        "y1": bbox[3],
                                    }
                                    for bbox in location.bounding_boxes
                                ],
                            }
                            for location in marker.locations
                        ],
                    }
                )

    output = {
        "source_file": result.source_file,
        "citations": citations,
    }
    if result.warnings:
        output["warnings"] = result.warnings
    return output


def citation_sentence_list_to_json(
    result: CitationSentenceList,
    indent: int = 2,
) -> str:
    """Serialize extracted citation sentences as UTF-8-safe JSON."""

    return json.dumps(
        citation_sentence_list_to_dict(result),
        ensure_ascii=False,
        indent=indent,
    )


def save_citation_sentence_list_json(
    result: CitationSentenceList,
    output_path: Path,
) -> Path:
    """Write extracted citation sentences to a JSON file."""

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        citation_sentence_list_to_json(result),
        encoding="utf-8",
    )
    return output_path
