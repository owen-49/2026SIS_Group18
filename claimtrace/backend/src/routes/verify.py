"""Claim verification endpoints."""

from fastapi import APIRouter, HTTPException

from ..models import MatchResult, VerdictEnum, VerifyRequest, VerifyResponse

router = APIRouter()


@router.post("/verify", response_model=VerifyResponse)
async def verify_claim(request: VerifyRequest):
    """Verify a single claim against its cited source paper.

    The source paper must have been previously uploaded via POST /api/parse.

    Returns the verdict (SUPPORT/PARTIAL/CONTRADICT/NOT_FOUND) with
    matching passages and rationale.
    """
    # TODO W3-W4: Wire to engine.retriever + engine.verifier
    # For now, return a stub response

    if not request.claim.strip():
        raise HTTPException(status_code=400, detail="Claim text is required.")

    # Placeholder — real verification will call Pair 2's engine
    return VerifyResponse(
        claim=request.claim,
        verdict=VerdictEnum.NOT_FOUND,
        confidence=0.0,
        rationale="Verification engine not yet integrated. This is a placeholder response.",
        matches=[
            MatchResult(
                passage_text="(Stub: source passage will appear here after W3 integration)",
                similarity=0.0,
                entailment_label=VerdictEnum.NOT_FOUND,
                confidence=0.0,
            )
        ],
    )
