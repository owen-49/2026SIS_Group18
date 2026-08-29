"""Parse and persist uploaded BibTeX files."""

from dataclasses import asdict
from pathlib import Path

from engine.bib_parser import parse_bib_file

from ..models import BibEntryRecord, PaperRecord, ParsedBibDocument, ParseStatus
from ..storage.bib_document_store import BibDocumentStoreError, save_bib_document
from ..storage.paper_store import PaperStoreError, get_paper, update_paper


class BibPaperNotFoundError(RuntimeError):
    """Raised when a requested uploaded file does not exist."""


class InvalidBibPaperError(RuntimeError):
    """Raised when a file cannot be used as a BibTeX document."""


class BibProcessingError(RuntimeError):
    """Raised when BibTeX parsing or persistence fails unexpectedly."""


def process_uploaded_bib(paper_id: str) -> PaperRecord:
    """Parse a persisted .bib upload, save its entries, and update its status."""
    try:
        record = get_paper(paper_id)
    except PaperStoreError as exc:
        raise BibProcessingError("Unable to read uploaded file metadata.") from exc

    if record is None:
        raise BibPaperNotFoundError("BibTeX file not found.")
    if record.file_type != "bib":
        raise InvalidBibPaperError("The uploaded file is not a BibTeX file.")

    try:
        processing = update_paper(
            paper_id,
            {"status": ParseStatus.PROCESSING, "error_message": None},
        )
        if processing is None:
            raise BibPaperNotFoundError("BibTeX file not found.")

        entries = parse_bib_file(Path(processing.file_path))
        if not entries:
            raise InvalidBibPaperError("No BibTeX entries were found in the uploaded file.")

        document = ParsedBibDocument(
            paper_id=paper_id,
            entries=[BibEntryRecord.model_validate(asdict(entry)) for entry in entries],
        )
        parsed_path = save_bib_document(document)
        completed = update_paper(
            paper_id,
            {
                "status": ParseStatus.COMPLETED,
                "entry_count": len(document.entries),
                "parsed_result_path": str(parsed_path),
                "error_message": None,
            },
        )
        if completed is None:
            raise BibPaperNotFoundError("BibTeX file not found.")
        return completed
    except InvalidBibPaperError as exc:
        _mark_failed(paper_id, str(exc))
        raise
    except BibPaperNotFoundError:
        raise
    except (BibDocumentStoreError, PaperStoreError, OSError, ValueError) as exc:
        _mark_failed(paper_id, "Unable to parse the uploaded BibTeX file.")
        raise BibProcessingError("Unable to process the uploaded BibTeX file.") from exc


def _mark_failed(paper_id: str, message: str) -> None:
    try:
        update_paper(
            paper_id,
            {"status": ParseStatus.FAILED, "error_message": message},
        )
    except PaperStoreError:
        pass
