"""Synchronous upload-to-Parser orchestration for the local MVP."""

from pathlib import Path

from ..models import PaperRecord, ParseStatus
from ..storage.paper_store import PaperStoreError, get_paper, update_paper
from ..storage.parsed_document_store import (
    ParsedDocumentStoreError,
    save_parsed_document,
)
from .parser_adapter import ParserAdapterError, parse_document


class PipelineError(RuntimeError):
    """Raised when a persisted upload cannot complete synchronous parsing."""


def process_uploaded_paper(paper_id: str) -> PaperRecord:
    """Parse a persisted PDF synchronously and update its metadata."""
    try:
        record = get_paper(paper_id)
    except PaperStoreError as exc:
        raise PipelineError("Unable to read uploaded paper metadata.") from exc

    if record is None:
        raise PipelineError("Uploaded paper record was not found.")
    if record.file_type != "pdf":
        return record

    try:
        processing = update_paper(
            paper_id,
            {"status": ParseStatus.PROCESSING, "error_message": None},
        )
        if processing is None:
            raise PipelineError("Uploaded paper record was not found.")

        parsed = parse_document(
            paper_id,
            Path(processing.file_path),
            title=processing.title,
        )
        parsed_path = save_parsed_document(parsed)
        completed = update_paper(
            paper_id,
            {
                "status": ParseStatus.COMPLETED,
                "pages": parsed.pages,
                "paragraph_count": len(parsed.paragraphs),
                "title": parsed.title,
                "parsed_result_path": str(parsed_path),
                "error_message": None,
            },
        )
        if completed is None:
            raise PipelineError("Uploaded paper record was not found.")
        return completed
    except (
        PipelineError,
        PaperStoreError,
        ParsedDocumentStoreError,
        ParserAdapterError,
        OSError,
    ) as exc:
        try:
            update_paper(
                paper_id,
                {
                    "status": ParseStatus.FAILED,
                    "error_message": "Unable to prepare the uploaded PDF for verification.",
                },
            )
        except PaperStoreError:
            pass
        raise PipelineError("Unable to process the uploaded PDF.") from exc
