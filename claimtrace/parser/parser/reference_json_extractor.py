"""Reference-list extraction from academic PDF documents.

The PDF layout and reading order are handled by OpenDataLoader PDF.
This module contains ClaimTrace-specific logic:

1. Locate the References/Bibliography section.
2. Collect its document elements.
3. Split those elements into individual reference entries.
4. Preserve each entry as source text.
5. Parse APA 7 and standard IEEE metadata when possible.
6. Export every raw entry with nullable structured fields.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Protocol

import pymupdf

from .opendataloader_adapter import (
    ConvertedDocument,
    DocumentElement,
    convert_pdf,
)


class TextElement(Protocol):
    """Small structural interface used by the style classifier."""

    content: str


BRACKET_NUMBER_PATTERN = re.compile(r"^\s*\[\d+\]\s+")
PLAIN_NUMBER_PATTERN = re.compile(r"^\s*\d+[.)]\s+")
PARENTHESIZED_DATE_PATTERN = re.compile(
    r"\((?:(?:18|19|20)\d{2}[a-z]?|n\.?d\.?)"
    r"(?:,\s*[A-Za-z]+\s+\d{1,2})?\)",
    flags=re.IGNORECASE,
)
APA_AUTHOR_DATE_PATTERN = re.compile(
    r"^[^()]{2,180}?\.\s*"
    r"\((?:(?:18|19|20)\d{2}[a-z]?|n\.?d\.?)"
    r"(?:,\s*[A-Za-z]+\s+\d{1,2})?\)\.",
    flags=re.IGNORECASE,
)
AUTHOR_LEAD_PATTERN = re.compile(
    r"^[A-Z\u00c0-\u024f][\w\u00c0-\u024f'\u2019-]+"
    r"(?:,|\s+[A-Z]{1,4}(?:\s|,))"
)
AUTHOR_TITLE_PATTERN = re.compile(
    r"^[A-Z\u00c0-\u024f][\w\u00c0-\u024f'\u2019-]+,\s+"
    r"[A-Z\u00c0-\u024f][^()]{2,120}\."
)
INLINE_AUTHOR_YEAR_START_PATTERN = re.compile(
    r"(?<![\w])"
    r"(?:"
    r"[A-Z\u00c0-\u024f][\w\u00c0-\u024f'\u2019-]+"
    r"(?:,\s*|\s+)[A-Z]{1,4}(?:\.|\b)"
    r"(?:[A-Za-z\u00c0-\u024f'\u2019.,&\s-]{0,160}?)"
    r"|"
    r"[A-Z\u00c0-\u024f][A-Za-z\u00c0-\u024f'\u2019-]+"
    r"(?:\s+[A-Z\u00c0-\u024f][A-Za-z\u00c0-\u024f'\u2019-]+){1,8}\."
    r")\s*"
    r"\((?:(?:18|19|20)\d{2}[a-z]?|n\.?d\.?)"
    r"(?:,\s*[A-Za-z]+\s+\d{1,2})?\)",
)


@dataclass(frozen=True)
class ReferenceStyleDetection:
    """Detected reference family plus inspectable scoring evidence."""

    family: str
    confidence: float
    evidence: dict[str, float] = field(default_factory=dict)


def _ratio(count: int, total: int) -> float:
    return round(count / total, 3) if total else 0.0


def looks_like_reference_start(text: str) -> bool:
    """Return whether text has a common reference-entry opening."""

    normalized = " ".join(text.split()).strip()
    if not normalized:
        return False

    if BRACKET_NUMBER_PATTERN.match(normalized) or PLAIN_NUMBER_PATTERN.match(normalized):
        return True

    author_year = INLINE_AUTHOR_YEAR_START_PATTERN.match(normalized)
    if author_year and author_year.end() <= 220:
        return True

    if APA_AUTHOR_DATE_PATTERN.match(normalized[:240]):
        return True

    return bool(AUTHOR_TITLE_PATTERN.match(normalized[:180]))


def find_author_year_starts(text: str) -> list[int]:
    """Find likely author-year entry starts inside one text element."""

    return [match.start() for match in INLINE_AUTHOR_YEAR_START_PATTERN.finditer(text)]


def detect_reference_family(
    elements: Iterable[TextElement],
    sample_size: int = 30,
) -> ReferenceStyleDetection:
    """Classify a reference list using several weak signals together."""

    texts = [
        " ".join(element.content.split()).strip() for element in elements if element.content.strip()
    ][:sample_size]
    total = len(texts)

    if not total:
        return ReferenceStyleDetection("unknown", 0.0, {"sample_size": 0.0})

    bracketed = sum(bool(BRACKET_NUMBER_PATTERN.match(text)) for text in texts)
    plain = sum(bool(PLAIN_NUMBER_PATTERN.match(text)) for text in texts)
    parenthesized_date = sum(bool(PARENTHESIZED_DATE_PATTERN.search(text[:220])) for text in texts)
    apa_date = sum(bool(APA_AUTHOR_DATE_PATTERN.search(text[:240])) for text in texts)
    author_lead = sum(bool(AUTHOR_LEAD_PATTERN.search(text[:180])) for text in texts)
    author_title = sum(bool(AUTHOR_TITLE_PATTERN.search(text[:180])) for text in texts)

    evidence = {
        "sample_size": float(total),
        "bracketed_number_ratio": _ratio(bracketed, total),
        "plain_number_ratio": _ratio(plain, total),
        "parenthesized_date_ratio": _ratio(parenthesized_date, total),
        "apa_punctuation_ratio": _ratio(apa_date, total),
        "author_lead_ratio": _ratio(author_lead, total),
        "author_title_ratio": _ratio(author_title, total),
    }

    minimum_repeated_signal = 2 if total >= 2 else 1

    if bracketed >= minimum_repeated_signal and bracketed >= plain:
        return ReferenceStyleDetection(
            "bracket-numbered",
            min(1.0, 0.55 + 0.45 * bracketed / total),
            evidence,
        )

    if plain >= minimum_repeated_signal:
        return ReferenceStyleDetection(
            "plain-numbered",
            min(1.0, 0.55 + 0.45 * plain / total),
            evidence,
        )

    if parenthesized_date >= minimum_repeated_signal:
        apa_share = apa_date / parenthesized_date
        if apa_share >= 0.55:
            return ReferenceStyleDetection(
                "author-year-parenthesized",
                min(0.98, 0.5 + 0.3 * parenthesized_date / total + 0.18 * apa_share),
                evidence,
            )

        if author_lead >= minimum_repeated_signal:
            return ReferenceStyleDetection(
                "author-year-inline",
                min(0.95, 0.48 + 0.35 * parenthesized_date / total),
                evidence,
            )

    if author_title >= minimum_repeated_signal and parenthesized_date == 0:
        return ReferenceStyleDetection(
            "author-title",
            min(0.85, 0.45 + 0.35 * author_title / total),
            evidence,
        )

    return ReferenceStyleDetection(
        "unknown-unnumbered",
        max(0.1, min(0.49, 0.2 + 0.2 * author_lead / total)),
        evidence,
    )


@dataclass(frozen=True)
class PDFTextLine:
    """One text line with its one-indexed page and PDF coordinates."""

    text: str
    page: int
    bbox: tuple[float, float, float, float]


@dataclass
class LayoutReferenceCandidate:
    """Reference text assembled from hanging-indent lines."""

    text: str
    pages: list[int] = field(default_factory=list)
    bounding_boxes: list[tuple[float, float, float, float]] = field(default_factory=list)


def _normalise_label(text: str) -> str:
    value = " ".join(text.lower().split()).strip()
    return re.sub(r"[:.\s]+$", "", value)


def _line_from_dict(line: dict, page_number: int) -> PDFTextLine | None:
    spans = line.get("spans", [])
    text = "".join(str(span.get("text", "")) for span in spans).strip()
    bbox = line.get("bbox")

    if not text or not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
        return None

    return PDFTextLine(
        text=text,
        page=page_number,
        bbox=tuple(float(value) for value in bbox),
    )


def extract_reference_lines(
    pdf_path: Path,
    start_page: int,
    heading: str,
) -> list[PDFTextLine]:
    """Read reference-region text lines from a PDF using PyMuPDF."""

    lines: list[PDFTextLine] = []
    heading_label = _normalise_label(heading)

    with pymupdf.open(Path(pdf_path)) as document:
        first_page_index = max(0, start_page - 1)

        for page_index in range(first_page_index, len(document)):
            page = document[page_index]
            page_number = page_index + 1
            page_lines: list[PDFTextLine] = []

            for block in page.get_text("dict", sort=True).get("blocks", []):
                for raw_line in block.get("lines", []):
                    line = _line_from_dict(raw_line, page_number)
                    if line is not None:
                        page_lines.append(line)

            top_boundary = 44.0
            if page_index == first_page_index:
                matching_headings = [
                    line for line in page_lines if _normalise_label(line.text) == heading_label
                ]
                if matching_headings:
                    top_boundary = max(line.bbox[3] for line in matching_headings)

            for line in page_lines:
                if line.bbox[1] <= top_boundary:
                    continue
                if line.bbox[3] >= page.rect.height - 30.0:
                    continue
                if re.fullmatch(r"\s*\d+\s*", line.text):
                    continue
                lines.append(line)

    return lines


def _append_line(
    candidate: LayoutReferenceCandidate,
    line: PDFTextLine,
) -> None:
    separator = "" if candidate.text.rstrip().endswith("-") else " "
    candidate.text = f"{candidate.text.rstrip()}{separator}{line.text.lstrip()}"

    if line.page not in candidate.pages:
        candidate.pages.append(line.page)
    candidate.bounding_boxes.append(line.bbox)


def _hanging_indent_column_boundary(
    lines: list[PDFTextLine],
) -> float | None:
    """Return a likely gutter between two reference-list columns."""

    x_positions = sorted({round(line.bbox[0], 1) for line in lines})
    gaps = [
        (right - left, (left + right) / 2)
        for left, right in zip(x_positions, x_positions[1:])
    ]
    largest_gap, boundary = max(gaps, default=(0.0, 0.0))

    if largest_gap < 40.0:
        return None

    left_count = sum(line.bbox[0] <= boundary for line in lines)
    right_count = len(lines) - left_count
    return boundary if left_count >= 2 and right_count >= 2 else None


def _ordered_lines_with_column_bases(
    lines: list[PDFTextLine],
) -> list[tuple[PDFTextLine, float]]:
    """Order lines by page and column and attach each column's base x."""

    boundary = _hanging_indent_column_boundary(lines)
    if boundary is None:
        base_x = min(line.bbox[0] for line in lines)
        return [(line, base_x) for line in lines]

    left_lines = [line for line in lines if line.bbox[0] <= boundary]
    right_lines = [line for line in lines if line.bbox[0] > boundary]
    column_bases = (
        min(line.bbox[0] for line in left_lines),
        min(line.bbox[0] for line in right_lines),
    )

    pages: dict[int, list[PDFTextLine]] = {}
    for line in lines:
        pages.setdefault(line.page, []).append(line)

    ordered: list[tuple[PDFTextLine, float]] = []
    for page in sorted(pages):
        page_lines = pages[page]
        for column, base_x in (
            ([line for line in page_lines if line.bbox[0] <= boundary], column_bases[0]),
            ([line for line in page_lines if line.bbox[0] > boundary], column_bases[1]),
        ):
            ordered.extend((line, base_x) for line in column)

    return ordered


def split_hanging_indent_lines(
    lines: list[PDFTextLine],
    x_tolerance: float = 4.0,
    minimum_indent: float = 5.0,
) -> list[LayoutReferenceCandidate]:
    """Split lines where flush-left lines start hanging-indent entries.

    An empty result means the lines do not contain strong enough hanging-
    indent evidence, allowing the caller to retain the normal extraction.
    """

    if len(lines) < 4:
        return []

    ordered_lines = _ordered_lines_with_column_bases(lines)
    flush_left = [
        line for line, base_x in ordered_lines if line.bbox[0] <= base_x + x_tolerance
    ]
    indented = [
        line for line, base_x in ordered_lines if line.bbox[0] >= base_x + minimum_indent
    ]

    if len(flush_left) < 2 or len(indented) < 2:
        return []

    candidates: list[LayoutReferenceCandidate] = []
    current: LayoutReferenceCandidate | None = None

    for line, base_x in ordered_lines:
        starts_entry = line.bbox[0] <= base_x + x_tolerance

        if starts_entry:
            if current is not None and current.text.strip():
                candidates.append(current)
            current = LayoutReferenceCandidate(
                text=line.text.strip(),
                pages=[line.page],
                bounding_boxes=[line.bbox],
            )
        elif current is not None:
            _append_line(current, line)

    if current is not None and current.text.strip():
        candidates.append(current)

    return candidates


REFERENCE_HEADINGS = {
    "references",
    "reference",
    "bibliography",
    "works cited",
    "literature cited",
    "references and notes",
}

END_SECTION_HEADINGS = {
    "appendix",
    "appendices",
    "acknowledgement",
    "acknowledgements",
    "acknowledgment",
    "acknowledgments",
    "author biography",
    "author biographies",
    "supplementary material",
    "supplemental material",
}

REFERENCE_TERMINATOR_PATTERN = re.compile(
    r"^\s*(?:publisher['\u2019]s\s+note\b|copyright\b|\u00a9\s*|"
    r"springer\s+nature\s+or\s+its\s+licensor\b)",
    flags=re.IGNORECASE,
)

NUMBERED_REFERENCE_PATTERN = re.compile(
    r"^\s*(?:\[(?P<bracket_number>\d+)\]|"
    r"(?P<plain_number>\d+)[.)])\s*"
)

INLINE_REFERENCE_START_PATTERN = re.compile(r"(?m)(?=^\s*(?:\[\d+\]|\d+[.)])\s+)")

DOI_PATTERN = re.compile(
    r"\b(?P<doi>10\.\d{4,9}/[-._;()/:A-Z0-9]+)",
    flags=re.IGNORECASE,
)
APA_METADATA_PATTERN = re.compile(
    r"^(?P<authors>.+?)\s*\("
    r"(?P<year>(?:(?:18|19|20)\d{2})[a-z]?|n\.?d\.?)"
    r"(?:,\s*[A-Za-z]+\s+\d{1,2})?"
    r"\)\.\s*(?P<body>.+)$",
    flags=re.IGNORECASE,
)
IEEE_METADATA_PATTERN = re.compile(
    r"^(?P<authors>.+?),\s*[\"\u00aa\u201c]"
    r"(?P<title>.+?),?[\"\u00ba\u201d]\s*,?\s*(?P<body>.+)$",
    flags=re.IGNORECASE,
)
APA_PERSON_PATTERN = re.compile(
    r"(?P<surname>[A-Z\u00c0-\u024f][A-Za-z\u00c0-\u024f'\u2019 -]+),\s*"
    r"(?P<initials>(?:[A-Za-z]\.(?:[-\s]*[A-Za-z]\.)*))",
)


@dataclass
class Reference:
    """One extracted reference-list entry."""

    raw_text: str = ""
    number: int | None = None
    page_start: int | None = None
    page_end: int | None = None
    bounding_boxes: list[tuple[float, float, float, float]] = field(default_factory=list)
    authors: list[str] | None = None
    year: int | None = None
    title: str | None = None
    venue: str | None = None
    doi: str | None = None


@dataclass
class ReferenceList:
    """Complete reference list extracted from one PDF."""

    source_file: str = ""
    references: list[Reference] = field(default_factory=list)
    start_page: int | None = None
    end_page: int | None = None
    heading: str | None = None
    style: str = "unknown"
    style_confidence: float = 0.0
    style_evidence: dict[str, float] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


@dataclass
class ReferenceSection:
    """Location of the reference-list heading in document order."""

    heading_index: int
    heading: str
    page: int
    body_prefix: str | None = None


@dataclass
class ReferenceCandidate:
    """Intermediate reference text before field extraction."""

    text: str
    pages: list[int] = field(default_factory=list)
    bounding_boxes: list[tuple[float, float, float, float]] = field(default_factory=list)


@dataclass(frozen=True)
class ParsedReferenceMetadata:
    """Structured fields recovered from one supported bibliography style."""

    authors: list[str] | None = None
    year: int | None = None
    title: str | None = None
    venue: str | None = None
    doi: str | None = None


def _normalise_heading(text: str) -> str:
    """Normalize a possible section heading."""

    value = text.strip().lower()
    value = re.sub(r"^\s*\d+(?:\.\d+)*[.)]?\s*", "", value)
    value = re.sub(r"[:.\s]+$", "", value)
    value = re.sub(r"\s+", " ", value)
    return value


def _reference_heading_parts(element: DocumentElement) -> tuple[str, str | None] | None:
    """Return a reference heading and an optional paragraph prefix.

    Two-column layout extraction can append a visually separate ``REFERENCES``
    heading to the final paragraph in the preceding column. Embedded recovery is
    deliberately limited to an uppercase heading at the end of an element so a
    prose phrase such as ``see references`` cannot start a bibliography.
    """

    if _normalise_heading(element.content) in REFERENCE_HEADINGS:
        return element.content.strip(), None

    heading_choices = sorted(REFERENCE_HEADINGS, key=len, reverse=True)
    match = re.search(
        rf"(?P<prefix>.+?)\s+(?P<heading>{'|'.join(map(re.escape, heading_choices))})"
        r"\s*[:.]?\s*$",
        element.content,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if match is None or not match.group("heading").isupper():
        return None

    prefix = match.group("prefix").strip()
    if not prefix or prefix[-1] not in ".!?":
        return None
    return match.group("heading").strip(), prefix


def _is_reference_terminator(element: DocumentElement) -> bool:
    """Return whether an element begins material after the bibliography."""

    if REFERENCE_TERMINATOR_PATTERN.match(element.content):
        return True

    if element.element_type != "heading":
        return False

    heading = _normalise_heading(element.content)
    return (
        heading in END_SECTION_HEADINGS
        or heading.startswith("appendix ")
        or heading.startswith("author bio")
    )


def _column_boundary(elements: list[DocumentElement]) -> float | None:
    """Return the strongest two-column gutter boundary, when present."""

    x_positions = sorted(
        {round(element.bbox[0], 1) for element in elements if element.bbox is not None}
    )
    gaps = [(right - left, (left + right) / 2) for left, right in zip(x_positions, x_positions[1:])]
    largest_gap, boundary = max(gaps, default=(0.0, 0.0))

    # Typical hanging indentation is much smaller than a column gutter.
    return boundary if largest_gap >= 40.0 else None


def _prior_later_column_references(
    document: ConvertedDocument,
    heading_index: int,
) -> list[DocumentElement]:
    """Recover references in a later column ordered before the heading.

    Layout engines commonly serialize a page column-by-column. When a
    References heading starts low in the left column, references at the top
    of the right column can therefore appear before the heading in document
    order even though they logically follow it.
    """

    heading = document.elements[heading_index]
    if heading.bbox is None:
        return []

    page_candidates = [
        element
        for element in document.elements
        if element.page == heading.page
        and (element is heading or looks_like_reference_start(element.content))
    ]
    boundary = _column_boundary(page_candidates)

    if boundary is None or heading.bbox[0] > boundary:
        return []

    return [
        element
        for element in document.elements[:heading_index]
        if element.page == heading.page
        and element.bbox is not None
        and element.bbox[0] > boundary
        and looks_like_reference_start(element.content)
    ]


def _count_reference_like_entries_after(
    document: ConvertedDocument,
    heading_index: int,
    lookahead: int = 25,
) -> int:
    """Count plausible entries after a heading candidate."""

    following_elements = document.elements[heading_index + 1 : heading_index + 1 + lookahead]
    recovered_elements = _prior_later_column_references(
        document,
        heading_index,
    )

    return sum(
        looks_like_reference_start(element.content)
        for element in following_elements + recovered_elements
    )


def find_reference_section(
    document: ConvertedDocument,
) -> ReferenceSection | None:
    """Locate the most credible References/Bibliography heading.

    A valid candidate must:

    1. Match a known heading, including a safely recoverable merged heading.
    2. Appear in the latter part of the paper.
    3. Be followed by at least two reference-like entries.

    Candidates classified as headings by OpenDataLoader are preferred.
    """

    if not document.elements:
        return None

    minimum_page = max(1, int(document.page_count * 0.4))
    candidates: list[
        tuple[int, int, int, DocumentElement, tuple[str, str | None]]
    ] = []

    for index, element in enumerate(document.elements):
        heading_parts = _reference_heading_parts(element)
        if heading_parts is None:
            continue

        if element.page < minimum_page:
            continue

        following_entry_count = _count_reference_like_entries_after(
            document,
            heading_index=index,
        )

        # A section heading should be followed by actual reference-like text.
        # This prevents table columns named "Reference" from being accepted,
        # while allowing unnumbered APA/Springer/MLA bibliographies.
        if following_entry_count < 2:
            continue

        heading_type_score = 1 if element.element_type == "heading" else 0

        candidates.append(
            (
                heading_type_score,
                following_entry_count,
                element.page,
                element,
                heading_parts,
            )
        )

    if not candidates:
        return None

    # Prefer a real heading, then the candidate followed by the largest
    # number of reference-like entries, then the later page.
    candidates.sort(
        key=lambda candidate: (
            candidate[0],
            candidate[1],
            candidate[2],
        ),
        reverse=True,
    )

    chosen_element = candidates[0][3]
    chosen_heading, body_prefix = candidates[0][4]
    chosen_index = document.elements.index(chosen_element)

    return ReferenceSection(
        heading_index=chosen_index,
        heading=chosen_heading,
        page=chosen_element.page,
        body_prefix=body_prefix,
    )


def collect_reference_elements(
    document: ConvertedDocument,
    section: ReferenceSection,
) -> list[DocumentElement]:
    """Collect the logical reference region around the section heading.

    Collection includes later columns that a layout engine emitted before
    the heading, and stops at a recognized post-reference heading.
    """

    collected = _prior_later_column_references(
        document,
        section.heading_index,
    )

    for element in document.elements[section.heading_index + 1 :]:
        if _is_reference_terminator(element):
            break

        if not element.content.strip():
            continue

        if element.element_type in {
            "header",
            "footer",
            "page number",
            "page-number",
        }:
            continue

        collected.append(element)

    return collected


def detect_reference_style(elements: list[DocumentElement]) -> str:
    """Return the detected family name for backwards compatibility."""

    return detect_reference_family(elements).family


def _split_element_text(text: str) -> list[str]:
    """Split one element when it contains several numbered references."""

    parts = [part.strip() for part in INLINE_REFERENCE_START_PATTERN.split(text) if part.strip()]

    return parts or [text.strip()]


def _split_unnumbered_element_text(text: str) -> list[str]:
    """Split multiple author-year references merged into one element."""

    starts = find_author_year_starts(text)
    if not starts:
        return [text.strip()] if text.strip() else []

    # A merged block can begin with the previous reference's continuation.
    # In that case the first detected author-year start is also a boundary.
    boundaries = starts[1:] if starts[0] == 0 else starts
    if not boundaries:
        return [text.strip()] if text.strip() else []
    parts: list[str] = []
    previous = 0

    for boundary in boundaries:
        part = text[previous:boundary].strip()
        if part:
            parts.append(part)
        previous = boundary

    final_part = text[previous:].strip()
    if final_part:
        parts.append(final_part)

    return parts


def _bbox_column_order(
    page_elements: list[tuple[int, DocumentElement]],
) -> list[DocumentElement]:
    """Order one page by columns, then from top to bottom."""

    positioned = [item for item in page_elements if item[1].bbox is not None]
    if len(positioned) < 2:
        return [element for _, element in page_elements]

    boundary = _column_boundary([element for _, element in positioned])
    if boundary is None:
        return [element for _, element in page_elements]

    left_column: list[tuple[int, DocumentElement]] = []
    right_column: list[tuple[int, DocumentElement]] = []
    unpositioned: list[tuple[int, DocumentElement]] = []

    for item in page_elements:
        bbox = item[1].bbox
        if bbox is None:
            unpositioned.append(item)
        elif bbox[0] <= boundary:
            left_column.append(item)
        else:
            right_column.append(item)

    def top_to_bottom(item: tuple[int, DocumentElement]) -> tuple[float, int]:
        bbox = item[1].bbox
        return (-(bbox[1] if bbox else 0.0), item[0])

    left_column.sort(key=top_to_bottom)
    right_column.sort(key=top_to_bottom)
    unpositioned.sort(key=lambda item: item[0])

    return [element for _, element in left_column + right_column + unpositioned]


def order_reference_elements(
    elements: list[DocumentElement],
) -> list[DocumentElement]:
    """Restore page and two-column reading order from bounding boxes."""

    pages: dict[int, list[tuple[int, DocumentElement]]] = {}
    for index, element in enumerate(elements):
        pages.setdefault(element.page, []).append((index, element))

    ordered: list[DocumentElement] = []
    for page in sorted(pages):
        ordered.extend(_bbox_column_order(pages[page]))

    return ordered


def _append_candidate_metadata(
    candidate: ReferenceCandidate,
    element: DocumentElement,
) -> None:
    if element.page and element.page not in candidate.pages:
        candidate.pages.append(element.page)

    if element.bbox is not None and element.bbox not in candidate.bounding_boxes:
        candidate.bounding_boxes.append(element.bbox)


def split_reference_entries(
    elements: list[DocumentElement],
    style: str | None = None,
) -> list[ReferenceCandidate]:
    """Split ordered elements into individual reference candidates.

    A numbered marker starts a new entry. Text without a marker is
    appended to the current entry, allowing references to span several
    document elements.
    """

    ordered_elements = order_reference_elements(elements)
    resolved_style = style or detect_reference_style(ordered_elements)
    is_numbered = resolved_style in {
        "bracket-numbered",
        "plain-numbered",
    }

    candidates: list[ReferenceCandidate] = []
    current: ReferenceCandidate | None = None

    for element in ordered_elements:
        parts = (
            _split_element_text(element.content)
            if is_numbered
            else _split_unnumbered_element_text(element.content)
        )

        for part in parts:
            starts_new_entry = (
                NUMBERED_REFERENCE_PATTERN.match(part) is not None
                if is_numbered
                else looks_like_reference_start(part)
            )

            # PDF blocks describe layout, not citation boundaries. Only a
            # style-specific marker is allowed to begin a new entry.
            if starts_new_entry:
                if current and current.text.strip():
                    candidates.append(current)
                current = ReferenceCandidate(text=part)
            elif current is None and not is_numbered:
                current = ReferenceCandidate(text=part)
            elif current is not None:
                current.text = f"{current.text} {part}".strip()

            if current is not None:
                _append_candidate_metadata(current, element)

    if current and current.text.strip():
        candidates.append(current)

    return candidates


def _extract_number(text: str) -> int | None:
    """Extract a leading reference number."""

    match = NUMBERED_REFERENCE_PATTERN.match(text)

    if not match:
        return None

    raw_number = match.group("bracket_number") or match.group("plain_number")
    return int(raw_number)


def _strip_reference_number(text: str) -> str:
    """Remove a leading bracketed or plain reference-list number."""

    return NUMBERED_REFERENCE_PATTERN.sub("", text, count=1).strip()


def _extract_doi(text: str) -> str | None:
    """Return a normalized DOI without URL or ``doi:`` decoration."""

    match = DOI_PATTERN.search(text)
    if match is None:
        return None
    doi = match.group("doi").rstrip(".,;")
    while doi.endswith(")") and doi.count(")") > doi.count("("):
        doi = doi[:-1]
    return doi


def _without_doi(text: str) -> str:
    """Remove DOI text before extracting a venue."""

    match = DOI_PATTERN.search(text)
    if match is None:
        return text.strip()

    prefix = text[: match.start()]
    prefix = re.sub(
        r"(?:https?://(?:dx\.)?doi\.org/|doi\s*:\s*)$",
        "",
        prefix,
        flags=re.IGNORECASE,
    )
    return prefix.rstrip(" ,.;")


def _clean_field(value: str) -> str | None:
    """Normalize whitespace and surrounding bibliography punctuation."""

    cleaned = " ".join(value.split()).strip(" \t\n\r,.;\"\u201c\u201d")
    return cleaned or None


def _year_to_int(value: str) -> int | None:
    """Return the four-digit part of a date, or ``None`` for no date."""

    match = re.search(r"(?:18|19|20)\d{2}", value)
    return int(match.group(0)) if match else None


def _split_title_from_source(body: str) -> tuple[str | None, str | None]:
    """Split a title sentence from the following source description."""

    for index, character in enumerate(body):
        if character not in ".!?" or index + 1 >= len(body):
            continue
        if not body[index + 1].isspace():
            continue
        if character == ".":
            prefix = body[: index + 1]
            if re.search(r"(?:\b[A-Z]\.){1,}$", prefix):
                continue
            if prefix.casefold().endswith(("e.g.", "i.e.", "et al.")):
                continue

        title = _clean_field(body[: index + 1])
        source = _clean_field(body[index + 1 :])
        if title and source:
            return title, source
    return None, None


def _parse_apa_authors(authors_text: str) -> list[str] | None:
    """Parse a complete APA author field without accepting trailing title text."""

    matches = list(APA_PERSON_PATTERN.finditer(authors_text))
    authors = [
        f"{match.group('surname').strip()}, {match.group('initials').strip()}"
        for match in matches
    ]
    if authors:
        residue = APA_PERSON_PATTERN.sub("", authors_text)
        residue = re.sub(r"\bet\s+al\.?", "", residue, flags=re.IGNORECASE)
        residue = re.sub(r"\band\b", "", residue, flags=re.IGNORECASE)
        if not re.sub(r"[\s,&.]+", "", residue):
            return authors
        return None

    corporate = _clean_field(authors_text.rstrip("."))
    if (
        corporate
        and "," not in corporate
        and ":" not in corporate
        and len(corporate.split()) <= 12
    ):
        return [corporate]
    return None


def _parse_apa_metadata(text: str) -> ParsedReferenceMetadata | None:
    """Parse the stable author/date/title/source sequence used by APA 7."""

    match = APA_METADATA_PATTERN.match(_strip_reference_number(text))
    if match is None:
        return None

    title, source = _split_title_from_source(match.group("body"))
    if title is None:
        return None

    authors = _parse_apa_authors(match.group("authors"))
    if authors is None:
        return None

    source_without_doi = _without_doi(source or "")
    venue = _clean_field(source_without_doi.split(",", 1)[0])
    return ParsedReferenceMetadata(
        authors=authors,
        year=_year_to_int(match.group("year")),
        title=title,
        venue=venue,
        doi=_extract_doi(text),
    )


def _parse_ieee_authors(authors_text: str) -> list[str] | None:
    """Split IEEE display-order author names."""

    normalized = re.sub(r",?\s+and\s+", ", ", authors_text, flags=re.IGNORECASE)
    authors = [
        cleaned
        for part in normalized.split(",")
        if (cleaned := _clean_field(part)) and cleaned.casefold() != "et al"
    ]
    return authors or None


def _parse_ieee_metadata(text: str) -> ParsedReferenceMetadata | None:
    """Parse IEEE entries whose article or paper title is quoted."""

    match = IEEE_METADATA_PATTERN.match(_strip_reference_number(text))
    if match is None:
        return None

    body_without_doi = _without_doi(match.group("body"))
    year_matches = list(re.finditer(r"\b(?:18|19|20)\d{2}\b", body_without_doi))
    if not year_matches:
        return None

    venue = re.split(
        r",\s*(?=(?:vol\.|no\.|pp?\.|art\.\s*no\.|(?:18|19|20)\d{2}\b))",
        body_without_doi,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    return ParsedReferenceMetadata(
        authors=_parse_ieee_authors(match.group("authors")),
        year=int(year_matches[-1].group(0)),
        title=_clean_field(match.group("title")),
        venue=_clean_field(venue),
        doi=_extract_doi(text),
    )


def parse_reference_metadata(text: str) -> ParsedReferenceMetadata:
    """Parse supported styles, or return an all-null metadata record."""

    for parser in (
        _parse_apa_metadata,
        _parse_ieee_metadata,
    ):
        metadata = parser(text)
        if metadata is not None:
            return metadata
    return ParsedReferenceMetadata()


def parse_reference_candidate(
    candidate: ReferenceCandidate,
) -> Reference:
    """Convert a candidate into the minimal internal reference record."""

    raw_text = " ".join(candidate.text.split()).strip()
    pages = sorted(set(candidate.pages))
    metadata = parse_reference_metadata(raw_text)

    return Reference(
        raw_text=raw_text,
        authors=metadata.authors,
        year=metadata.year,
        title=metadata.title,
        venue=metadata.venue,
        doi=metadata.doi,
        number=_extract_number(raw_text),
        page_start=pages[0] if pages else None,
        page_end=pages[-1] if pages else None,
        bounding_boxes=candidate.bounding_boxes,
    )


def _reference_numbering_warning(
    references: list[Reference],
) -> str | None:
    """Describe missing or out-of-order numbered references."""

    numbers = [reference.number for reference in references if reference.number is not None]
    if len(numbers) < 2:
        return None

    missing_ranges: list[str] = []
    out_of_order = False

    if numbers[0] > 1:
        end = numbers[0] - 1
        missing_ranges.append("1" if end == 1 else f"1-{end}")

    for current, following in zip(numbers, numbers[1:]):
        if following > current + 1:
            start = current + 1
            end = following - 1
            missing_ranges.append(str(start) if start == end else f"{start}-{end}")
        elif following <= current:
            out_of_order = True

    details: list[str] = []
    if missing_ranges:
        details.append(f"missing {', '.join(missing_ranges)}")
    if out_of_order:
        details.append("duplicate or out-of-order numbers")

    if not details:
        return None

    return f"Reference numbering is discontinuous ({'; '.join(details)})."


def extract_references_from_document(
    document: ConvertedDocument,
) -> ReferenceList:
    """Extract the reference list from a converted document."""

    section = find_reference_section(document)

    if section is None:
        return ReferenceList(
            source_file=document.file_name,
            warnings=["Reference-list heading was not found."],
        )

    elements = collect_reference_elements(document, section)
    style_detection = detect_reference_family(elements)
    candidates = split_reference_entries(
        elements,
        style=style_detection.family,
    )

    references = [
        parse_reference_candidate(candidate) for candidate in candidates if candidate.text.strip()
    ]

    warnings: list[str] = []

    if style_detection.confidence < 0.5:
        warnings.append(
            "Reference style was not recognized confidently. "
            "Entry boundaries may require manual review."
        )

    if not references:
        warnings.append("The reference heading was found, but no entries were extracted.")

    numbering_warning = _reference_numbering_warning(references)
    if numbering_warning:
        warnings.append(numbering_warning)

    return ReferenceList(
        source_file=document.file_name,
        references=references,
        start_page=section.page,
        end_page=(
            max(
                (reference.page_end for reference in references if reference.page_end is not None),
                default=section.page,
            )
        ),
        heading=section.heading,
        style=style_detection.family,
        style_confidence=style_detection.confidence,
        style_evidence=style_detection.evidence,
        warnings=warnings,
    )


def extract_references(pdf_path: Path) -> ReferenceList:
    """Convert a PDF and extract its reference list."""

    document = convert_pdf(Path(pdf_path))
    result = extract_references_from_document(document)

    if not _needs_hanging_indent_fallback(document, result):
        return result

    section = find_reference_section(document)
    if section is None:
        return result

    lines = extract_reference_lines(
        Path(pdf_path),
        start_page=section.page,
        heading=section.heading,
    )
    layout_candidates = split_hanging_indent_lines(lines)

    if not _layout_candidates_are_better(layout_candidates, result):
        return result

    candidates = [
        ReferenceCandidate(
            text=candidate.text,
            pages=candidate.pages,
            bounding_boxes=candidate.bounding_boxes,
        )
        for candidate in layout_candidates
    ]
    result.references = [parse_reference_candidate(candidate) for candidate in candidates]
    result.end_page = max(
        (reference.page_end for reference in result.references if reference.page_end is not None),
        default=result.start_page,
    )
    return result


def _needs_hanging_indent_fallback(
    document: ConvertedDocument,
    result: ReferenceList,
) -> bool:
    """Return whether OpenDataLoader probably merged APA entries."""

    if result.style != "author-year-parenthesized":
        return False

    section = find_reference_section(document)
    if section is None:
        return False

    elements = collect_reference_elements(document, section)
    if len(elements) < 2:
        return False

    detected_starts = sum(len(find_author_year_starts(element.content)) for element in elements)
    return detected_starts > len(elements) * 1.25


def _layout_candidates_are_better(
    candidates: list[LayoutReferenceCandidate],
    result: ReferenceList,
) -> bool:
    """Accept a layout recovery only when it is larger and coherent."""

    if len(candidates) <= len(result.references) or len(candidates) < 2:
        return False

    recognizable = sum(looks_like_reference_start(candidate.text) for candidate in candidates)
    return recognizable / len(candidates) >= 0.8


def reference_list_to_dict(reference_list: ReferenceList) -> dict:
    """Convert references to a stable raw-text-plus-metadata JSON schema."""

    output = {
        "source_file": reference_list.source_file,
        "references": [
            {
                "raw_text": reference.raw_text,
                "authors": reference.authors,
                "year": reference.year,
                "title": reference.title,
                "venue": reference.venue,
                "doi": reference.doi,
            }
            for reference in reference_list.references
        ],
    }
    if reference_list.warnings:
        output["warnings"] = reference_list.warnings
    return output


def reference_list_to_json(
    reference_list: ReferenceList,
    indent: int = 2,
) -> str:
    """Serialize a ReferenceList to JSON."""

    return json.dumps(
        reference_list_to_dict(reference_list),
        ensure_ascii=False,
        indent=indent,
    )


def save_reference_list_json(
    reference_list: ReferenceList,
    output_path: Path,
) -> Path:
    """Write a ReferenceList JSON file."""

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        reference_list_to_json(reference_list),
        encoding="utf-8",
    )
    return output_path
