"""BibTeX parsing and cross-verification endpoints."""

from pathlib import Path

from fastapi import APIRouter, HTTPException

from ..models import (
    BibEntryRecord,
    BibEntryVerificationResult,
    BibFieldResult,
    BibFieldStatusEnum,
    BibParseRequest,
    BibParseResponse,
    BibVerifyRequest,
    BibVerifyResponse,
)
from ..services.bib_service import (
    BibPaperNotFoundError,
    BibProcessingError,
    InvalidBibPaperError,
    process_uploaded_bib,
)
from ..services.bib_verification_service import (
    BibVerificationNotFoundError,
    BibVerificationNotReadyError,
    BibVerificationServiceError,
    InvalidBibVerificationError,
    verify_persisted_bib,
)
from ..storage.bib_document_store import BibDocumentStoreError, load_bib_document

router = APIRouter()


@router.post("/parse/bib", response_model=BibParseResponse)
async def parse_bib(request: BibParseRequest):
    """Reprocess an uploaded .bib file and return its persisted entries.

    POST /api/parse already parses and persists BibTeX uploads. This endpoint
    keeps the older two-step flow while exposing the structured entries that
    were actually saved for later verification.
    """
    try:
        record = process_uploaded_bib(request.paper_id)
    except BibPaperNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidBibPaperError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except BibProcessingError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if not record.parsed_result_path:
        raise HTTPException(status_code=500, detail="Parsed BibTeX output is missing.")

    try:
        document = load_bib_document(Path(record.parsed_result_path))
    except BibDocumentStoreError as exc:
        raise HTTPException(
            status_code=500,
            detail="Unable to read parsed BibTeX entries.",
        ) from exc

    if document.paper_id != record.paper_id:
        raise HTTPException(status_code=500, detail="Parsed BibTeX ID does not match the request.")

    return BibParseResponse(
        paper_id=record.paper_id,
        status=record.status,
        entry_count=len(document.entries),
        title=record.title,
        entries=[BibEntryRecord.model_validate(entry) for entry in document.entries],
    )


@router.post("/verify/bib", response_model=BibVerifyResponse)
async def verify_bib(request: BibVerifyRequest):
    """Cross-verify .bib entries against source PDF metadata.

    For each bib entry, compares title, year, authors, venue, and DOI
    against what's actually printed on the source PDF.

    Returns a per-field comparison with MATCH/MISMATCH/BIB_MISSING/PDF_MISSING status.
    """
    try:
        results = verify_persisted_bib(
            request.bib_paper_id,
            request.source_paper_ids,
        )
    except BibVerificationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except BibVerificationNotReadyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except InvalidBibVerificationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except BibVerificationServiceError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    bib_results = [_bib_result_to_response(result) for result in results]

    return BibVerifyResponse(
        bib_paper_id=request.bib_paper_id,
        total_entries=len(results),
        matched_entries=sum(
            1 for result in results if not result.has_errors and result.warning_count == 0
        ),
        error_entries=sum(1 for result in results if result.has_errors),
        results=bib_results,
    )


def _bib_result_to_response(
    result,
) -> BibEntryVerificationResult:
    """Convert engine BibVerificationResult to API response model."""
    fields = [
        BibFieldResult(
            field_name=f.field_name,
            bib_value=f.bib_value,
            pdf_value=f.pdf_value,
            status=BibFieldStatusEnum(f.status.value),
            detail=f.detail,
        )
        for f in result.fields
    ]

    return BibEntryVerificationResult(
        citation_key=result.citation_key,
        has_errors=result.has_errors,
        error_count=result.error_count,
        warning_count=result.warning_count,
        summary=result.summary,
        fields=fields,
    )
