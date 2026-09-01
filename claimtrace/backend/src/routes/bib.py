"""BibTeX parsing and cross-verification endpoints."""

from fastapi import APIRouter, HTTPException

from ..models import (
    BibEntryVerificationResult,
    BibFieldResult,
    BibFieldStatusEnum,
    BibParseRequest,
    BibVerifyRequest,
    BibVerifyResponse,
    ParseResponse,
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

router = APIRouter()


@router.post("/parse/bib", response_model=ParseResponse)
async def parse_bib(request: BibParseRequest):
    """Compatibility endpoint for reprocessing an uploaded .bib file.

    POST /api/parse already parses BibTeX uploads. This endpoint reuses the
    same service for clients that still use the older two-step flow.
    """
    try:
        record = process_uploaded_bib(request.paper_id)
        return ParseResponse(
            paper_id=record.paper_id,
            status=record.status,
            file_type=record.file_type,
            pages=record.pages,
            paragraph_count=record.paragraph_count,
            entry_count=record.entry_count,
            title=record.title,
        )
    except BibPaperNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidBibPaperError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except BibProcessingError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


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
