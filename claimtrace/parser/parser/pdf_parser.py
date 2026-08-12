"""Core PDF parser for academic papers.

Handles:
- Text extraction with position metadata
- Two-column layout reordering
- Hyphenation repair
- Paragraph boundary recovery
"""

from dataclasses import dataclass, field
from pathlib import Path

import fitz  # PyMuPDF


@dataclass
class TextBlock:
    """A block of text extracted from a PDF page."""

    text: str
    bbox: tuple[float, float, float, float]  # (x0, y0, x1, y1)
    page: int
    block_type: str = "text"  # "text", "title", "figure", "table"


@dataclass
class Paragraph:
    """A recovered paragraph with positional metadata."""

    text: str
    page_start: int
    page_end: int
    bbox: tuple[float, float, float, float] | None = None
    section_heading: str | None = None


@dataclass
class ParsedPaper:
    """Complete output of PDF parsing."""

    file_path: Path
    title: str | None = None
    authors: list[str] = field(default_factory=list)
    paragraphs: list[Paragraph] = field(default_factory=list)
    raw_blocks: list[TextBlock] = field(default_factory=list)
    pages: int = 0


def extract_blocks(pdf_path: Path) -> list[TextBlock]:
    """Extract all text blocks from a PDF with position metadata.

    Args:
        pdf_path: Path to the PDF file.

    Returns:
        List of TextBlock objects with text and positional bounding boxes.
    """
    doc = fitz.open(str(pdf_path))
    blocks: list[TextBlock] = []

    for page_num, page in enumerate(doc, start=1):
        raw_blocks = page.get_text("blocks")
        for block in raw_blocks:
            x0, y0, x1, y1, text, block_type, _ = block
            text = text.strip()
            if not text:
                continue
            blocks.append(
                TextBlock(
                    text=text,
                    bbox=(x0, y0, x1, y1),
                    page=page_num,
                    block_type="text" if block_type == 0 else "other",
                )
            )

    doc.close()
    return blocks


def reorder_two_column(blocks: list[TextBlock], page_width: float) -> list[TextBlock]:
    """Reorder blocks from a two-column layout into reading order.

    Strategy: Sort blocks first by vertical position (y0), then detect
    the column boundary at page_width / 2. Blocks in the left half are
    read before blocks in the right half within the same vertical band.

    Args:
        blocks: TextBlocks from a single page.
        page_width: Total width of the page in points.

    Returns:
        Reordered list of TextBlock objects.
    """
    if not blocks:
        return blocks

    mid_line = page_width / 2
    left_col = [b for b in blocks if b.bbox[0] < mid_line]
    right_col = [b for b in blocks if b.bbox[0] >= mid_line]

    left_col.sort(key=lambda b: (b.bbox[1], b.bbox[0]))
    right_col.sort(key=lambda b: (b.bbox[1], b.bbox[0]))

    # Interleave: merge left and right columns by vertical bands
    result: list[TextBlock] = []
    li, ri = 0, 0
    band_height = 20  # tolerance in points for same-line blocks

    while li < len(left_col) or ri < len(right_col):
        if li < len(left_col) and (
            ri >= len(right_col) or left_col[li].bbox[1] <= right_col[ri].bbox[1] + band_height
        ):
            result.append(left_col[li])
            li += 1
        else:
            result.append(right_col[ri])
            ri += 1

    return result


def repair_hyphenation(text: str) -> str:
    """Fix broken hyphenation at line boundaries.

    Example:
        "repre-\nsentation" → "representation"

    Args:
        text: Raw text that may contain soft-hyphen line breaks.

    Returns:
        Text with hyphenation repaired.
    """
    import re

    return re.sub(r"(\w+)-\n(\w+)", r"\1\2", text)


def recover_paragraphs(blocks: list[TextBlock]) -> list[Paragraph]:
    """Merge consecutive text blocks into paragraphs.

    Uses vertical gap detection: two blocks belong to the same paragraph
    if they are close together vertically and horizontally aligned.

    Args:
        blocks: Ordered list of TextBlock objects.

    Returns:
        List of Paragraph objects.
    """
    if not blocks:
        return []

    paragraphs: list[Paragraph] = []
    current_lines: list[str] = []
    page_start = blocks[0].page
    prev_block: TextBlock | None = None

    for block in blocks:
        if prev_block and block.page == prev_block.page:
            gap = block.bbox[1] - prev_block.bbox[3]
            # If gap is large, consider it a new paragraph
            if gap > prev_block.bbox[3] - prev_block.bbox[1]:  # gap > line height
                if current_lines:
                    paragraphs.append(
                        Paragraph(
                            text=" ".join(current_lines),
                            page_start=page_start,
                            page_end=prev_block.page,
                        )
                    )
                current_lines = [repair_hyphenation(block.text)]
                page_start = block.page
            else:
                current_lines.append(repair_hyphenation(block.text))
        else:
            if prev_block and block.page != prev_block.page and current_lines:
                paragraphs.append(
                    Paragraph(
                        text=" ".join(current_lines),
                        page_start=page_start,
                        page_end=prev_block.page,
                    )
                )
                current_lines = []
                page_start = block.page
            current_lines.append(repair_hyphenation(block.text))

        prev_block = block

    # Don't forget the last paragraph
    if current_lines:
        paragraphs.append(
            Paragraph(
                text=" ".join(current_lines),
                page_start=page_start,
                page_end=prev_block.page if prev_block else page_start,
            )
        )

    return paragraphs


def parse_pdf(pdf_path: Path) -> ParsedPaper:
    """Full PDF parsing pipeline.

    Args:
        pdf_path: Path to the academic paper PDF.

    Returns:
        ParsedPaper with extracted text blocks and recovered paragraphs.
    """
    doc = fitz.open(str(pdf_path))
    page_width = doc[0].rect.width if len(doc) > 0 else 612
    doc.close()

    blocks = extract_blocks(pdf_path)

    # Reorder two-column layouts
    pages_raw: dict[int, list[TextBlock]] = {}
    for block in blocks:
        pages_raw.setdefault(block.page, []).append(block)

    reordered: list[TextBlock] = []
    for page_blocks in pages_raw.values():
        reordered.extend(reorder_two_column(page_blocks, page_width))

    paragraphs = recover_paragraphs(reordered)

    return ParsedPaper(
        file_path=pdf_path,
        paragraphs=paragraphs,
        raw_blocks=blocks,
        pages=len(pages_raw),
    )
