"""Reference-list extraction from academic PDF documents.

The PDF layout and reading order are handled by OpenDataLoader PDF.
This module contains ClaimTrace-specific logic:

1. Locate the References/Bibliography section.
2. Collect its document elements.
3. Split those elements into individual reference entries.
4. Preserve each entry as source text.
5. Export a minimal JSON representation for the backend and frontend.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from opendataloader_adapter import (
    ConvertedDocument,
    DocumentElement,
    convert_pdf,
)
from reference_line_extractor import (
    LayoutReferenceCandidate,
    extract_reference_lines,
    split_hanging_indent_lines,
)
from reference_style import (
    detect_reference_family,
    find_author_year_starts,
    looks_like_reference_start,
)

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

INLINE_REFERENCE_START_PATTERN = re.compile(
    r"(?m)(?=^\s*(?:\[\d+\]|\d+[.)])\s+)"
)

@dataclass
class Reference:
    """One extracted reference-list entry."""

    raw_text: str = ""
    number: int | None = None
    page_start: int | None = None
    page_end: int | None = None
    bounding_boxes: list[tuple[float, float, float, float]] = field(
        default_factory=list
    )


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


@dataclass
class ReferenceCandidate:
    """Intermediate reference text before field extraction."""

    text: str
    pages: list[int] = field(default_factory=list)
    bounding_boxes: list[tuple[float, float, float, float]] = field(
        default_factory=list
    )


def _normalise_heading(text: str) -> str:
    """Normalize a possible section heading."""

    value = text.strip().lower()
    value = re.sub(r"^\s*\d+(?:\.\d+)*[.)]?\s*", "", value)
    value = re.sub(r"[:.\s]+$", "", value)
    value = re.sub(r"\s+", " ", value)
    return value


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
        {
            round(element.bbox[0], 1)
            for element in elements
            if element.bbox is not None
        }
    )
    gaps = [
        (right - left, (left + right) / 2)
        for left, right in zip(x_positions, x_positions[1:])
    ]
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
        and (
            element is heading
            or looks_like_reference_start(element.content)
        )
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

    following_elements = document.elements[
        heading_index + 1 : heading_index + 1 + lookahead
    ]
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

    1. Exactly match a known reference-list heading.
    2. Appear in the latter part of the paper.
    3. Be followed by at least two reference-like entries.

    Candidates classified as headings by OpenDataLoader are preferred.
    """

    if not document.elements:
        return None

    minimum_page = max(1, int(document.page_count * 0.4))
    candidates: list[tuple[int, int, int, DocumentElement]] = []

    for index, element in enumerate(document.elements):
        heading = _normalise_heading(element.content)

        if heading not in REFERENCE_HEADINGS:
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

        heading_type_score = (
            1 if element.element_type == "heading" else 0
        )

        candidates.append(
            (
                heading_type_score,
                following_entry_count,
                element.page,
                element,
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
    chosen_index = document.elements.index(chosen_element)

    return ReferenceSection(
        heading_index=chosen_index,
        heading=chosen_element.content.strip(),
        page=chosen_element.page,
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

    parts = [
        part.strip()
        for part in INLINE_REFERENCE_START_PATTERN.split(text)
        if part.strip()
    ]

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

    return [
        element
        for _, element in left_column + right_column + unpositioned
    ]


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

    if (
        element.bbox is not None
        and element.bbox not in candidate.bounding_boxes
    ):
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


def parse_reference_candidate(
    candidate: ReferenceCandidate,
) -> Reference:
    """Convert a candidate into the minimal internal reference record."""

    raw_text = " ".join(candidate.text.split()).strip()
    pages = sorted(set(candidate.pages))

    return Reference(
        raw_text=raw_text,
        number=_extract_number(raw_text),
        page_start=pages[0] if pages else None,
        page_end=pages[-1] if pages else None,
        bounding_boxes=candidate.bounding_boxes,
    )


def _reference_numbering_warning(
    references: list[Reference],
) -> str | None:
    """Describe missing or out-of-order numbered references."""

    numbers = [
        reference.number
        for reference in references
        if reference.number is not None
    ]
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
            missing_ranges.append(
                str(start) if start == end else f"{start}-{end}"
            )
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
        parse_reference_candidate(candidate)
        for candidate in candidates
        if candidate.text.strip()
    ]

    warnings: list[str] = []

    if style_detection.confidence < 0.5:
        warnings.append(
            "Reference style was not recognized confidently. "
            "Entry boundaries may require manual review."
        )

    if not references:
        warnings.append(
            "The reference heading was found, but no entries were extracted."
        )

    numbering_warning = _reference_numbering_warning(references)
    if numbering_warning:
        warnings.append(numbering_warning)

    return ReferenceList(
        source_file=document.file_name,
        references=references,
        start_page=section.page,
        end_page=(
            max(
                (
                    reference.page_end
                    for reference in references
                    if reference.page_end is not None
                ),
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
    result.references = [
        parse_reference_candidate(candidate)
        for candidate in candidates
    ]
    result.end_page = max(
        (
            reference.page_end
            for reference in result.references
            if reference.page_end is not None
        ),
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

    detected_starts = sum(
        len(find_author_year_starts(element.content))
        for element in elements
    )
    return detected_starts > len(elements) * 1.25


def _layout_candidates_are_better(
    candidates: list[LayoutReferenceCandidate],
    result: ReferenceList,
) -> bool:
    """Accept a layout recovery only when it is larger and coherent."""

    if len(candidates) <= len(result.references) or len(candidates) < 2:
        return False

    recognizable = sum(
        looks_like_reference_start(candidate.text)
        for candidate in candidates
    )
    return recognizable / len(candidates) >= 0.8


def reference_list_to_dict(reference_list: ReferenceList) -> dict:
    """Convert a reference list into the minimal public JSON format.

    Parsing metadata remains available on ``ReferenceList`` for internal
    diagnostics, but generated JSON deliberately contains only the source
    filename and the original text of each reference.
    """

    return {
        "source_file": reference_list.source_file,
        "references": [
            {"raw_text": reference.raw_text}
            for reference in reference_list.references
        ],
    }


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
