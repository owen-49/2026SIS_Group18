"""Line-layout fallback for hanging-indent reference lists.

OpenDataLoader normally provides the reading order used by ClaimTrace. Some
PDFs, however, merge many APA references into a few page-wide paragraphs.
For those documents only, this module reads the PDF's native text lines and
uses the hanging indent to recover entry boundaries.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf


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
    bounding_boxes: list[tuple[float, float, float, float]] = field(
        default_factory=list
    )


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
                    line
                    for line in page_lines
                    if _normalise_label(line.text) == heading_label
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

    left_edges = [line.bbox[0] for line in lines]
    base_x = min(left_edges)
    flush_left = [x for x in left_edges if x <= base_x + x_tolerance]
    indented = [x for x in left_edges if x >= base_x + minimum_indent]

    if len(flush_left) < 2 or len(indented) < 2:
        return []

    candidates: list[LayoutReferenceCandidate] = []
    current: LayoutReferenceCandidate | None = None

    for line in lines:
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
