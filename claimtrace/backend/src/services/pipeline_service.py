"""Upload parsing and the single worker background queue."""

import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from ..models import PaperRecord, PaperScope, ParseStatus
from ..storage import parsed_document_store
from ..storage.paper_store import PaperStoreError, get_paper, list_papers, update_paper
from ..storage.parsed_document_store import (
    ParsedDocumentStoreError,
    save_parsed_document,
)
from ..storage.reference_store import invalidate_references
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

        invalidate_references(paper_id)
        parsed_root = parsed_document_store.PARSED_DIR
        if processing.scope is PaperScope.VERIFY_SOURCE:
            parsed_root = parsed_root / "verify-sources"
        parsed = parse_document(
            paper_id,
            Path(processing.file_path),
            title=processing.title,
            output_dir=parsed_root / "markdown",
            # Source PDFs only need paragraph text and page numbers; the
            # slow AI hybrid backend is reserved for manuscripts.
            hybrid="off" if processing.scope is PaperScope.VERIFY_SOURCE else None,
        )
        parsed_path = save_parsed_document(parsed, parsed_dir=parsed_root)
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
        user_message = getattr(exc, "user_message", None)
        error_message = (
            user_message
            if isinstance(user_message, str) and user_message.strip()
            else "Unable to prepare the uploaded PDF for verification."
        )
        try:
            update_paper(
                paper_id,
                {
                    "status": ParseStatus.FAILED,
                    "error_message": error_message,
                },
            )
        except PaperStoreError:
            pass
        raise PipelineError("Unable to process the uploaded PDF.") from exc


logger = logging.getLogger(__name__)
executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="parse")


def _run_parse(paper_id: str) -> None:
    """Keep unexpected worker failures visible and persist a terminal status."""
    try:
        process_uploaded_paper(paper_id)
    except Exception:
        logger.exception("Background parsing failed for paper_id=%s", paper_id)
        try:
            record = get_paper(paper_id)
            if record is not None and record.status is not ParseStatus.FAILED:
                update_paper(
                    paper_id,
                    {
                        "status": ParseStatus.FAILED,
                        "error_message": "Unable to prepare the uploaded PDF for verification.",
                    },
                )
        except Exception:
            logger.exception("Unable to persist parse failure for paper_id=%s", paper_id)


def submit_parse(paper_id: str) -> None:
    """Enqueue a persisted PDF without waiting for parsing."""
    executor.submit(_run_parse, paper_id)


def shutdown_parse_queue() -> None:
    """Cancel queued work when the server stops."""
    executor.shutdown(wait=False, cancel_futures=True)


def recover_interrupted_parses() -> int:
    """Mark unfinished PDFs from the previous process as failed."""
    count = 0
    for record in list_papers():
        if record.file_type == "pdf" and record.status in {
            ParseStatus.PENDING,
            ParseStatus.PROCESSING,
        }:
            update_paper(
                record.paper_id,
                {
                    "status": ParseStatus.FAILED,
                    "error_message": (
                        "Parsing was interrupted by a server restart. Please upload the file again."
                    ),
                },
            )
            count += 1
    return count
