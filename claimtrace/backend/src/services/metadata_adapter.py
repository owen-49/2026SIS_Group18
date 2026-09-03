"""Adapt persisted Parser output to the Engine's PDF metadata contract."""

from engine.bib_verifier import PdfMetadata

from ..models import ParsedDocument


def pdf_metadata_from_parsed(document: ParsedDocument) -> PdfMetadata:
    """Build the Engine metadata contract from persisted Parser output."""
    return PdfMetadata(
        title=document.title or "",
        authors=list(document.authors),
        year=document.year,
        venue=document.venue or "",
        doi=document.doi or "",
    )
