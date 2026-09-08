"""Extract sentences containing supported in-text citations.

This module handles square-bracket styles such as ``[1]`` and ``[3, 4]``, plus
APA 7 author-year forms such as ``(Smith, 2020)`` and ``Smith et al. (2020)``.
It deliberately operates on OpenDataLoader document elements instead of raw
page text so that PDF layout artifacts can be filtered before extraction.
"""

from __future__ import annotations

import json
import re
import unicodedata
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
_AUTHOR_YEAR_PATTERN = r"(?:18|19|20)\d{2}[a-z]?|n\.?d\.?"
_REFERENCE_AUTHOR_YEAR_PATTERN = re.compile(
    rf"\((?P<year>{_AUTHOR_YEAR_PATTERN})\)",
    flags=re.IGNORECASE,
)
_PARENTHETICAL_AUTHOR_YEAR_PATTERN = re.compile(
    rf"\((?P<content>[^()]{{0,300}}?(?:{_AUTHOR_YEAR_PATTERN})[^()]*)\)",
    flags=re.IGNORECASE,
)
_CITATION_YEAR_PATTERN = re.compile(rf"(?<!\d)({_AUTHOR_YEAR_PATTERN})(?!\d)", re.IGNORECASE)
_APA_SURNAME_PATTERN = re.compile(
    r"(?:^|,\s*(?:&\s*)?)"
    r"(?P<surname>[A-Z\u00c0-\u024f][A-Za-z\u00c0-\u024f'\u2019 -]*?),\s*"
    r"(?=[A-Z])"
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


@dataclass(frozen=True)
class CitationLocation:
    """PDF coordinates that locate part of a cited sentence on one page."""

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
    source_spans: list[_SentenceSourceSpan] = field(default_factory=list)
    locations: list[CitationLocation] = field(default_factory=list)

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
    source_spans: list[_TextSourceSpan]


@dataclass(frozen=True)
class _TextSourceSpan:
    """Character range contributed by one document element to a text run."""

    element_id: str
    page: int
    start: int
    end: int


@dataclass(frozen=True)
class _SentenceSourceSpan:
    """Searchable part of a sentence contributed by one document element."""

    element_id: str
    page: int
    text: str


@dataclass(frozen=True)
class _AuthorYearReference:
    """Minimal author/year key used to link APA citations to references."""

    reference_id: int
    surnames: tuple[str, ...]
    year: str
    corporate_author: bool = False


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


def _normalise_author(value: str) -> str:
    """Normalize a person or organization name for citation matching."""

    decomposed = unicodedata.normalize("NFKD", value).casefold()
    return "".join(character for character in decomposed if character.isalnum())


def _normalise_year(value: str) -> str:
    """Normalize APA years, including letter suffixes and ``n.d.``."""

    return re.sub(r"[^a-z0-9]", "", value.casefold())


def _author_year_references(reference_list: ReferenceList) -> list[_AuthorYearReference]:
    """Build linkable APA author/year keys from reference-list entries."""

    keys: list[_AuthorYearReference] = []
    for reference_id, reference in enumerate(reference_list.references, start=1):
        date_match = _REFERENCE_AUTHOR_YEAR_PATTERN.search(reference.raw_text[:300])
        if date_match is None:
            continue

        author_text = reference.raw_text[: date_match.start()].strip().rstrip(". ")
        surnames = tuple(
            match.group("surname").strip()
            for match in _APA_SURNAME_PATTERN.finditer(author_text)
        )
        corporate_author = not surnames
        if corporate_author and author_text:
            surnames = (author_text,)
        if not surnames:
            continue

        keys.append(
            _AuthorYearReference(
                reference_id=reference_id,
                surnames=surnames,
                year=_normalise_year(date_match.group("year")),
                corporate_author=corporate_author,
            )
        )
    return keys


def _clean_citation_author(author_text: str) -> str:
    """Remove common APA signal phrases before an author name."""

    value = author_text.strip().strip(",")
    return re.sub(
        r"^(?:(?:see(?:\s+also)?|e\.g\.|cf\.|as\s+cited\s+in)\s+)+",
        "",
        value,
        flags=re.IGNORECASE,
    ).strip()


def _citation_author_matches(
    author_text: str,
    reference: _AuthorYearReference,
) -> bool:
    """Return whether an APA citation author label matches a reference key."""

    author_text = _clean_citation_author(author_text)
    if not author_text:
        return False

    normalized_surnames = tuple(_normalise_author(name) for name in reference.surnames)
    if reference.corporate_author:
        return _normalise_author(author_text) == normalized_surnames[0]

    if re.search(r"\bet\s+al\.?,?\s*$", author_text, flags=re.IGNORECASE):
        first_author = re.split(r"\bet\s+al\.", author_text, flags=re.IGNORECASE)[0]
        return _normalise_author(first_author) == normalized_surnames[0]

    cited_authors = re.split(r"\s+(?:&|and)\s+", author_text, flags=re.IGNORECASE)
    normalized_cited = tuple(_normalise_author(author) for author in cited_authors)
    if len(normalized_cited) > 1:
        return normalized_cited == normalized_surnames[: len(normalized_cited)]

    cited_author = normalized_cited[0]
    return cited_author == normalized_surnames[0] or cited_author.endswith(
        normalized_surnames[0]
    )


def _reference_ids_for_author_year(
    author_text: str,
    years: list[str],
    references: list[_AuthorYearReference],
) -> tuple[int, ...]:
    """Resolve an APA author plus one or more years to reference positions."""

    normalized_years = {_normalise_year(year) for year in years}
    return tuple(
        reference.reference_id
        for reference in references
        if reference.year in normalized_years
        and _citation_author_matches(author_text, reference)
    )


def _narrative_labels(reference: _AuthorYearReference) -> tuple[str, ...]:
    """Return valid narrative author labels for one APA reference."""

    if reference.corporate_author:
        return (reference.surnames[0],)
    if len(reference.surnames) == 1:
        return (reference.surnames[0],)
    if len(reference.surnames) == 2:
        first, second = reference.surnames
        return (f"{first} and {second}", f"{first} & {second}")
    return (f"{reference.surnames[0]} et al.",)


def _valid_apa_markers(
    sentence: str,
    references: list[_AuthorYearReference],
) -> list[CitationMarker]:
    """Find validated APA 7 parenthetical and narrative citations."""

    markers_by_span: dict[tuple[int, int], CitationMarker] = {}

    for match in _PARENTHETICAL_AUTHOR_YEAR_PATTERN.finditer(sentence):
        reference_ids: list[int] = []
        for citation_part in match.group("content").split(";"):
            year_matches = list(_CITATION_YEAR_PATTERN.finditer(citation_part))
            if not year_matches:
                continue
            author_text = citation_part[: year_matches[0].start()].rstrip(" ,")
            years = [year_match.group(1) for year_match in year_matches]
            reference_ids.extend(
                _reference_ids_for_author_year(author_text, years, references)
            )

        ordered_ids = tuple(dict.fromkeys(reference_ids))
        if ordered_ids:
            markers_by_span[(match.start(), match.end())] = CitationMarker(
                text=match.group(0),
                reference_ids=ordered_ids,
                start=match.start(),
                end=match.end(),
            )

    for reference in references:
        for label in _narrative_labels(reference):
            pattern = re.compile(
                rf"(?<![\w]){re.escape(label)}\s*"
                rf"\((?P<details>{_AUTHOR_YEAR_PATTERN}(?:\s*,[^()]*)?)\)",
                flags=re.IGNORECASE,
            )
            for match in pattern.finditer(sentence):
                if _normalise_year(
                    _CITATION_YEAR_PATTERN.search(match.group("details")).group(1)
                ) != reference.year:
                    continue
                span = (match.start(), match.end())
                existing = markers_by_span.get(span)
                if existing is None:
                    markers_by_span[span] = CitationMarker(
                        text=match.group(0),
                        reference_ids=(reference.reference_id,),
                        start=match.start(),
                        end=match.end(),
                    )
                elif reference.reference_id not in existing.reference_ids:
                    existing.reference_ids += (reference.reference_id,)

    return sorted(markers_by_span.values(), key=lambda marker: (marker.start, marker.end))


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
                    source_spans=[
                        _TextSourceSpan(
                            element_id=element.element_id,
                            page=element.page,
                            start=0,
                            end=len(normalized),
                        )
                    ],
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
            element_start = len(current.text) + 1
            current.text = f"{current.text} {normalized}"
            current.page_end = element.page
            current.source_element_ids.append(element.element_id)
            current.source_spans.append(
                _TextSourceSpan(
                    element_id=element.element_id,
                    page=element.page,
                    start=element_start,
                    end=element_start + len(normalized),
                )
            )
            continue

        if current is not None:
            merged.append(current)
        current = _TextRun(
            order=order,
            text=normalized,
            page_start=element.page,
            page_end=element.page,
            source_element_ids=[element.element_id],
            source_spans=[
                _TextSourceSpan(
                    element_id=element.element_id,
                    page=element.page,
                    start=0,
                    end=len(normalized),
                )
            ],
        )

    if current is not None:
        merged.append(current)

    return sorted([*standalone, *merged], key=lambda run: run.order)


def extract_citation_sentences_from_document(
    document: ConvertedDocument,
    reference_list: ReferenceList | None = None,
) -> CitationSentenceList:
    """Extract complete sentences containing validated supported citations."""

    resolved_references = reference_list or extract_references_from_document(document)
    valid_reference_ids = {
        reference.number
        for reference in resolved_references.references
        if reference.number is not None
    }
    author_year_references = (
        _author_year_references(resolved_references)
        if resolved_references.style == "author-year-parenthesized"
        else []
    )
    warnings: list[str] = []

    if not valid_reference_ids and not author_year_references:
        warnings.append(
            "No linkable numbered or author-year reference list was found; "
            "citation extraction was skipped."
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
            if valid_reference_ids:
                markers = _valid_markers(sentence, valid_reference_ids)
            else:
                markers = _valid_apa_markers(sentence, author_year_references)
            if not markers or not _looks_like_prose(sentence):
                continue

            sentence_number = len(sentences) + 1
            source_spans = []
            for source_span in run.source_spans:
                overlap_start = max(start, source_span.start)
                overlap_end = min(end, source_span.end)
                if overlap_start >= overlap_end:
                    continue
                span_text = run.text[overlap_start:overlap_end].strip()
                if span_text:
                    source_spans.append(
                        _SentenceSourceSpan(
                            element_id=source_span.element_id,
                            page=source_span.page,
                            text=span_text,
                        )
                    )
            sentences.append(
                CitedSentence(
                    sentence_id=f"citation-sentence-{sentence_number:04d}",
                    text=sentence,
                    markers=markers,
                    page_start=run.page_start or None,
                    page_end=run.page_end or None,
                    source_element_ids=run.source_element_ids,
                    source_spans=source_spans,
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


def _unique_rectangles(rectangles: list[pymupdf.Rect]) -> list[pymupdf.Rect]:
    """Remove duplicate search hits while preserving reading order."""

    unique: dict[tuple[float, float, float, float], pymupdf.Rect] = {}
    for rectangle in rectangles:
        key = tuple(round(value, 3) for value in rectangle)
        unique.setdefault(key, rectangle)
    return sorted(unique.values(), key=lambda rectangle: (rectangle.y0, rectangle.x0))


def _merge_line_rectangles(rectangles: list[pymupdf.Rect]) -> list[pymupdf.Rect]:
    """Merge word or span rectangles that belong to the same visual line."""

    merged: list[pymupdf.Rect] = []
    for rectangle in _unique_rectangles(rectangles):
        if not merged:
            merged.append(pymupdf.Rect(rectangle))
            continue

        previous = merged[-1]
        overlap = min(previous.y1, rectangle.y1) - max(previous.y0, rectangle.y0)
        minimum_height = min(previous.height, rectangle.height)
        if minimum_height > 0 and overlap / minimum_height >= 0.6:
            previous.include_rect(rectangle)
        else:
            merged.append(pymupdf.Rect(rectangle))
    return merged


def _normalise_search_word(word: str) -> str:
    """Normalize a PDF or sentence word for layout-tolerant comparison."""

    decomposed = unicodedata.normalize("NFKD", word).casefold()
    return "".join(character for character in decomposed if character.isalnum())


def _matching_word_range(
    page_words: list[tuple],
    target_text: str,
    start_at: int = 0,
) -> tuple[int, int] | None:
    """Find a contiguous PDF-word range, allowing line-break hyphenation."""

    target_words = [
        normalized
        for word in target_text.split()
        if (normalized := _normalise_search_word(word))
    ]
    normalized_page_words = [_normalise_search_word(str(word[4])) for word in page_words]
    if not target_words:
        return None

    for start in range(start_at, len(page_words)):
        if not normalized_page_words[start]:
            continue

        page_index = start
        target_index = 0
        page_value = normalized_page_words[page_index]
        target_value = target_words[target_index]

        while True:
            if page_value == target_value:
                page_index += 1
                target_index += 1
                if target_index == len(target_words):
                    return start, page_index
                if page_index == len(page_words):
                    break
                page_value = normalized_page_words[page_index]
                target_value = target_words[target_index]
            elif target_value.startswith(page_value) and page_index + 1 < len(page_words):
                page_index += 1
                page_value += normalized_page_words[page_index]
            elif page_value.startswith(target_value) and target_index + 1 < len(target_words):
                target_index += 1
                target_value += target_words[target_index]
            else:
                break

    return None


def _anchored_word_range(
    page_words: list[tuple],
    target_text: str,
) -> tuple[int, int] | None:
    """Locate a sentence by stable start/end anchors when its middle differs."""

    target_words = target_text.split()
    if len(target_words) < 8:
        return None

    anchor_size = min(5, len(target_words) // 2)
    prefix_range = _matching_word_range(
        page_words,
        " ".join(target_words[:anchor_size]),
    )
    if prefix_range is None:
        return None

    suffix_range = _matching_word_range(
        page_words,
        " ".join(target_words[-anchor_size:]),
        start_at=prefix_range[1],
    )
    if suffix_range is None:
        return None
    return prefix_range[0], suffix_range[1]


def _search_sentence_words(
    page: pymupdf.Page,
    text: str,
    clip: pymupdf.Rect | None,
) -> list[pymupdf.Rect]:
    """Locate sentence text by matching normalized PDF words in sequence."""

    for search_clip in (clip, None) if clip is not None else (None,):
        page_words = list(page.get_text("words", clip=search_clip, sort=True))
        matched_range = _matching_word_range(page_words, text)
        if matched_range is None:
            matched_range = _anchored_word_range(page_words, text)
        if matched_range is None:
            continue

        start, end = matched_range
        rectangles = [pymupdf.Rect(*word[:4]) for word in page_words[start:end]]
        return _merge_line_rectangles(rectangles)

    return []


def _search_sentence_part(
    page: pymupdf.Page,
    text: str,
    clip: pymupdf.Rect | None,
) -> list[pymupdf.Rect]:
    """Find one sentence part, retrying without a layout clip when necessary."""

    rectangles = list(page.search_for(text, clip=clip))
    if not rectangles and clip is not None:
        rectangles = list(page.search_for(text))
    if rectangles:
        return _merge_line_rectangles(rectangles)
    return _search_sentence_words(page, text, clip)


def locate_citation_sentences(
    pdf_path: Path,
    document: ConvertedDocument,
    result: CitationSentenceList,
) -> CitationSentenceList:
    """Attach full-sentence PDF positions, grouped by page.

    A sentence can be composed from multiple OpenDataLoader elements. Each
    element's contribution is searched on its own page, so a sentence that
    crosses a page boundary produces one ``CitationLocation`` per page.
    """

    elements_by_id = {element.element_id: element for element in document.elements}

    with pymupdf.open(Path(pdf_path)) as pdf:
        for sentence in result.sentences:
            rectangles_by_page: dict[int, list[pymupdf.Rect]] = {}
            for source_span in sentence.source_spans:
                if not 1 <= source_span.page <= len(pdf):
                    continue

                element = elements_by_id.get(source_span.element_id)
                page = pdf[source_span.page - 1]
                clip = None
                if element is not None and element.bbox is not None:
                    clip = _opendataloader_bbox_to_pymupdf(
                        element.bbox,
                        page.rect.height,
                    )
                rectangles_by_page.setdefault(source_span.page, []).extend(
                    _search_sentence_part(page, source_span.text, clip)
                )

            sentence.locations = _locations_from_rectangles(
                {
                    page_number: _unique_rectangles(rectangles)
                    for page_number, rectangles in rectangles_by_page.items()
                }
            )

    return result


def locate_citation_markers(
    pdf_path: Path,
    document: ConvertedDocument,
    result: CitationSentenceList,
) -> CitationSentenceList:
    """Backward-compatible alias for full cited-sentence location."""

    return locate_citation_sentences(pdf_path, document, result)


def extract_citation_sentences(pdf_path: Path) -> CitationSentenceList:
    """Convert a PDF once, then extract its reference-linked sentences."""

    pdf_path = Path(pdf_path)
    document = convert_pdf(pdf_path)
    references = extract_references_from_document(document)
    result = extract_citation_sentences_from_document(document, references)
    return locate_citation_sentences(pdf_path, document, result)


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
                            for location in sentence.locations
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
