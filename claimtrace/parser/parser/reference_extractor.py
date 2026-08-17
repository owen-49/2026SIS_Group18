"""Reference list extraction and parsing.

Extracts the bibliography/references section from academic PDFs
and parses individual entries into structured data.
"""

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Reference:
    """A single parsed reference entry."""

    id: str  # e.g., "smith2023emergent"
    title: str | None = None
    authors: list[str] = field(default_factory=list)
    year: int | None = None
    venue: str | None = None
    raw_text: str = ""


@dataclass
class ReferenceList:
    """Complete bibliography extracted from a paper."""

    references: list[Reference] = field(default_factory=list)
    start_page: int | None = None
    end_page: int | None = None


def find_reference_section(text_blocks: list) -> int | None:
    """Locate the page where the reference section begins.

    Uses heuristics: looks for headings like 'References', 'Bibliography',
    'Literature Cited' in the last 20% of the document.

    Args:
        text_blocks: Ordered list of text blocks from the entire paper.

    Returns:
        Page number where references start, or None if not found.
    """
    REFERENCE_HEADINGS = {"references", "bibliography", "literature cited", "works cited"}

    # Search from the end: references are always at the back
    for block in reversed(text_blocks):
        heading = block.text.strip().lower().rstrip(".")
        if heading in REFERENCE_HEADINGS or any(
            h in heading for h in REFERENCE_HEADINGS
        ):
            return block.page

    return None


def parse_reference_text(raw_text: str) -> Reference:
    """Parse a single reference entry string into structured fields.

    Uses simple heuristics for common CS bibliography formats.
    v0.1 handles: "[N] Author(s). Title. Venue, Year."

    Args:
        raw_text: A single reference entry as a string.

    Returns:
        Reference with extracted fields.
    """
    import re

    ref = Reference(id="", raw_text=raw_text)

    # Try to extract year (four digits, 19xx-20xx)
    year_match = re.search(r"\b((?:19|20)\d{2})\b", raw_text)
    if year_match:
        ref.year = int(year_match.group(1))

    # Try to extract title (text in quotes or between "Title." and next period after venue)
    title_match = re.search(r'"([^"]+)"', raw_text)
    if title_match:
        ref.title = title_match.group(1)
    else:
        # Fallback: look for sentence-case sequence before venue pattern
        title_match = re.search(r'\.\s+([A-Z][^.?!]{20,200})[.?!]', raw_text)
        if title_match:
            ref.title = title_match.group(1).strip()

    # Generate a citation ID from first author + year
    author_match = re.match(r"^(?:\[\d+\]\s*)?([A-Z][a-z]+)", raw_text)
    if author_match and ref.year:
        ref.id = f"{author_match.group(1).lower()}{ref.year}"
    elif ref.year:
        ref.id = f"unknown{ref.year}"

    return ref


def extract_references(pdf_path: Path, parsed_paper) -> ReferenceList:
    """Extract and parse the reference list from a parsed paper.

    Args:
        pdf_path: Path to the PDF file.
        parsed_paper: ParsedPaper from pdf_parser.parse_pdf().

    Returns:
        ReferenceList with structured reference entries.
    """
    ref_page = find_reference_section(parsed_paper.raw_blocks)
    if ref_page is None:
        return ReferenceList()

    # Collect text from reference pages only
    ref_blocks = [b for b in parsed_paper.raw_blocks if b.page >= ref_page]
    full_text = "\n".join(b.text for b in ref_blocks)

    # Split into individual references
    # Common pattern: each reference starts with [N] or a newline after a period
    import re

    entries = re.split(r"\n(?=\[\d+\])", full_text)
    references = [parse_reference_text(entry) for entry in entries if entry.strip()]

    return ReferenceList(
        references=references,
        start_page=ref_page,
    )
