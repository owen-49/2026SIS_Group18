"""Adapt persisted Parser output to the Engine's PDF metadata contract."""

from engine.bib_verifier import PdfMetadata

from ..models import ParsedDocument


def pdf_metadata_from_parsed(document: ParsedDocument) -> PdfMetadata:
    """Build PdfMetadata while tolerating fields the Parser has not added yet."""
    return PdfMetadata(
        title=document.title or "",
        authors=list(getattr(document, "authors", None) or []),
        year=getattr(document, "year", None),
        venue=getattr(document, "venue", None) or "",
        doi=getattr(document, "doi", None) or "",
    )
