"""Claim verification endpoints."""

from fastapi import APIRouter, HTTPException

from ..models import VerifyRequest, VerifyResponse
from ..services.demo_service import build_demo_verification

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

    return build_demo_verification(
        claim=request.claim.strip(),
        source_paper_id=request.source_paper_id,
    )
