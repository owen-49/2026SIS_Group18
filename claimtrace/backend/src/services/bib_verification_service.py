"""Orchestrate persisted BibTeX and PDF metadata through the Engine verifier."""

from pathlib import Path

from engine.bib_parser import BibEntry, find_entry_by_title
from engine.bib_verifier import BibVerificationResult, PdfMetadata, verify_all_entries

from ..models import ParseStatus
from ..storage.bib_document_store import BibDocumentStoreError, load_bib_document
from ..storage.paper_store import PaperStoreError, get_paper
from ..storage.parsed_document_store import (
    ParsedDocumentStoreError,
    load_parsed_document,
)
from .metadata_adapter import pdf_metadata_from_parsed


class BibVerificationNotFoundError(RuntimeError):
    """Raised when the requested BibTeX upload does not exist."""


class BibVerificationNotReadyError(RuntimeError):
    """Raised when BibTeX parsing has not completed."""


class InvalidBibVerificationError(RuntimeError):
    """Raised when the requested file cannot be used for BibTeX verification."""


class BibVerificationServiceError(RuntimeError):
    """Raised when persisted data cannot be loaded or verified."""


def verify_persisted_bib(
    bib_paper_id: str,
    source_paper_ids: list[str],
) -> list[BibVerificationResult]:
    """Verify stored BibTeX entries against available source PDF metadata."""
    try:
        record = get_paper(bib_paper_id)
    except PaperStoreError as exc:
        raise BibVerificationServiceError("Unable to read BibTeX metadata.") from exc

    if record is None:
        raise BibVerificationNotFoundError("BibTeX file not found.")
    if record.file_type != "bib":
        raise InvalidBibVerificationError("The requested file is not a BibTeX file.")
    if record.status in {ParseStatus.PENDING, ParseStatus.PROCESSING}:
        raise BibVerificationNotReadyError("BibTeX parsing has not completed.")
    if record.status == ParseStatus.FAILED:
        raise InvalidBibVerificationError(record.error_message or "BibTeX parsing failed.")
    if not record.parsed_result_path:
        raise BibVerificationServiceError("Parsed BibTeX output is missing.")

    try:
        document = load_bib_document(Path(record.parsed_result_path))
        if document.paper_id != bib_paper_id:
            raise BibVerificationServiceError("Parsed BibTeX ID does not match the request.")
        entries = [BibEntry(**entry.model_dump()) for entry in document.entries]
        metadata_map = _load_pdf_metadata(entries, source_paper_ids)
        return verify_all_entries(entries, metadata_map)
    except BibDocumentStoreError as exc:
        raise BibVerificationServiceError("Unable to read parsed BibTeX entries.") from exc


def _load_pdf_metadata(
    entries: list[BibEntry],
    source_paper_ids: list[str],
) -> dict[str, PdfMetadata]:
    """Match usable PDF metadata to BibTeX entries by title."""
    metadata_map: dict[str, PdfMetadata] = {}

    for paper_id in source_paper_ids:
        try:
            record = get_paper(paper_id)
        except PaperStoreError as exc:
            raise BibVerificationServiceError("Unable to read source PDF metadata.") from exc

        if (
            record is None
            or record.file_type != "pdf"
            or record.status != ParseStatus.COMPLETED
            or not record.parsed_result_path
        ):
            continue

        try:
            parsed = load_parsed_document(Path(record.parsed_result_path))
        except ParsedDocumentStoreError as exc:
            raise BibVerificationServiceError("Unable to read parsed source PDF.") from exc
        if parsed.paper_id != paper_id:
            raise BibVerificationServiceError("Parsed source PDF ID does not match the request.")

        pdf_metadata = pdf_metadata_from_parsed(parsed)
        matching_entry = find_entry_by_title(entries, pdf_metadata.title)
        if matching_entry is not None:
            metadata_map.setdefault(matching_entry.key, pdf_metadata)

    return metadata_map
