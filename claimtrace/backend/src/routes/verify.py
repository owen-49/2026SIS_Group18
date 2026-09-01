"""Claim verification endpoints."""

from fastapi import APIRouter, HTTPException

from ..models import VerifyRequest, VerifyResponse
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
