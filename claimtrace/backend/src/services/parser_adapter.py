"""Stable adapter for Parser integration.

The Parser team implementation is still evolving. This module currently
returns deterministic mock paragraphs while preserving the file-based
contract that the real Parser will implement later.
"""

from pathlib import Path

from ..models import ParsedDocument, ParsedParagraph


class ParserAdapterError(RuntimeError):
    """Raised when an uploaded file cannot be prepared for parsing."""


def parse_document(
    paper_id: str,
    file_path: Path,
    *,
    title: str | None = None,
) -> ParsedDocument:
    """Return deterministic mock Parser output for an uploaded PDF."""
    if not file_path.is_file():
        raise ParserAdapterError(f"Uploaded file not found: {file_path}")
    if file_path.suffix.lower() != ".pdf":
        raise ParserAdapterError("The mock PDF Parser only accepts PDF files.")

    display_title = title or file_path.stem
    paragraphs = [
        ParsedParagraph(
            text=(
                f"The uploaded paper {display_title} was stored locally and prepared "
                "for citation verification."
            ),
            page_start=1,
            page_end=1,
        ),
        ParsedParagraph(
            text=(
                "The source describes how attention mechanisms can model relationships "
                "between positions without recurrent computation."
            ),
            page_start=1,
            page_end=1,
        ),
        ParsedParagraph(
            text=(
                "The authors note that verification quality depends on retrieving "
                "relevant source passages and preserving their context."
            ),
            page_start=2,
            page_end=2,
        ),
    ]

    return ParsedDocument(
        paper_id=paper_id,
        title=display_title,
        pages=2,
        paragraphs=paragraphs,
    )
