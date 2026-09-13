"""Claim verification endpoints."""

from fastapi import APIRouter, HTTPException

from ..models import (
    CitationComparisonRequest,
    CitationComparisonResponse,
    VerifyRequest,
    VerifyResponse,
)
from ..services.citation_comparison_service import (
    CitationComparisonError,
    ComparisonLLMNotConfiguredError,
    compare_claim_to_cited_paper,
)
from ..services.verification_service import (
    InvalidPaperError,
    PaperNotFoundError,
    PaperNotReadyError,
    VerificationServiceError,
    verify_paper_claim,
)

router = APIRouter()


@router.post("/verify", response_model=VerifyResponse)
async def verify_claim(request: VerifyRequest):
    """Verify a single claim against its cited source paper.

    The source paper must have been previously uploaded via POST /api/parse.

    Returns the verdict (SUPPORT/PARTIAL/CONTRADICT/NOT_FOUND) with
    matching passages and rationale.
    """
    if not request.claim.strip():
        raise HTTPException(status_code=400, detail="Claim text is required.")

    try:
        return verify_paper_claim(
            paper_id=request.source_paper_id,
            claim=request.claim.strip(),
        )
    except PaperNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PaperNotReadyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except InvalidPaperError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except VerificationServiceError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/verify/citation", response_model=CitationComparisonResponse)
def verify_citation_comparison(request: CitationComparisonRequest):
    """Compare one claim against the paper its citation marker points at.

    Unlike POST /api/verify, which takes an explicit ``source_paper_id``, this
    endpoint resolves the cited paper from the claim's own citation marker
    (``\\cite{wei2022emergent}``, ``(Wei, 2022)``, ...) against the uploaded
    bibliography, then semantically retrieves the relevant passages and asks the
    LLM whether they support the claim.

    Failures that still carry useful information — an unresolvable marker, a
    reference with no parsed PDF, a model error — are returned as HTTP 200 with
    a ``status`` other than ``COMPARED`` and ``judgement: null``. A non-COMPARED
    status means *the claim was not judged*; it never means the claim is
    unsupported.

    Declared ``def`` rather than ``async def`` on purpose: every step here is
    blocking (JSON reads, embedding on CPU, FAISS, a synchronous LLM call), so
    FastAPI must run it in a threadpool instead of stalling the event loop.
    """
    try:
        return compare_claim_to_cited_paper(
            claim=request.claim,
            citation_marker=request.citation_marker,
            manuscript_id=request.manuscript_id,
            claim_id=request.claim_id,
            k=request.k,
        )
    except ComparisonLLMNotConfiguredError as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "LLM_NOT_CONFIGURED", "message": str(exc)},
        ) from exc
    except CitationComparisonError as exc:
        raise HTTPException(
            status_code=500,
            detail={"code": "COMPARISON_FAILED", "message": str(exc)},
        ) from exc
