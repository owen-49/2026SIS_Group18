"""Orchestrate persisted Parser output through the Engine adapter."""

from pathlib import Path

from ..models import ParseStatus, VerifyResponse
from ..storage.paper_store import PaperStoreError, get_paper
from ..storage.parsed_document_store import (
    ParsedDocumentStoreError,
    load_parsed_document,
)
from .engine_adapter import EngineAdapterError, verify_claim


class PaperNotFoundError(RuntimeError):
    """Raised when a requested paper ID is unknown."""


class PaperNotReadyError(RuntimeError):
    """Raised when parsing has not completed."""


class InvalidPaperError(RuntimeError):
    """Raised when a paper cannot be used for claim verification."""


class VerificationServiceError(RuntimeError):
    """Raised when persisted data or Engine processing fails."""


def verify_paper_claim(paper_id: str, claim: str) -> VerifyResponse:
    """Verify a claim against parsed content for a real uploaded paper ID."""
    try:
        record = get_paper(paper_id)
    except PaperStoreError as exc:
        raise VerificationServiceError("Unable to read paper metadata.") from exc

    if record is None:
        raise PaperNotFoundError("Paper not found.")
    if record.file_type != "pdf":
        raise InvalidPaperError("Only parsed PDF files can be verified.")
    if record.status in {ParseStatus.PENDING, ParseStatus.PROCESSING}:
        raise PaperNotReadyError("Paper parsing has not completed.")
    if record.status == ParseStatus.FAILED:
        raise InvalidPaperError(record.error_message or "Paper parsing failed.")
    if not record.parsed_result_path:
        raise VerificationServiceError("Parsed paper output is missing.")

    try:
        document = load_parsed_document(Path(record.parsed_result_path))
        if document.paper_id != paper_id:
            raise VerificationServiceError("Parsed paper ID does not match the request.")
        return verify_claim(claim, document)
    except (ParsedDocumentStoreError, EngineAdapterError) as exc:
        raise VerificationServiceError("Unable to verify the claim.") from exc
