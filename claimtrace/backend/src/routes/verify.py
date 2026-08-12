"""Claim verification endpoints."""

from fastapi import APIRouter, HTTPException, Request

from ..models import MatchResult, VerdictEnum, VerifyRequest, VerifyResponse

router = APIRouter()


def _get_verifier(request: Request):
    """Build a Verifier from the app's configured LLM client.

    Centralised here so all verify/audit routes use the same setup.
    """
    from engine.verifier import Verifier

    llm_client = request.app.state.llm_client
    model = request.app.state.llm_model

    return Verifier(model=model), llm_client


@router.post("/verify", response_model=VerifyResponse)
async def verify_claim(request: VerifyRequest, req: Request):
    """Verify a single claim against its cited source paper.

    The source paper must have been previously uploaded via POST /api/parse.

    Returns the verdict (SUPPORT/PARTIAL/CONTRADICT/NOT_FOUND) with
    matching passages and rationale.
    """
    if not request.claim.strip():
        raise HTTPException(status_code=400, detail="Claim text is required.")

    # Import engine modules (lazy — only loaded when this endpoint is called)
    from engine.embedder import Embedder
    from engine.retriever import Retriever

    verifier, llm_client = _get_verifier(req)

    # For now: mock retrieval (no pre-built index).
    # Full pipeline (parse → embed → retrieve → verify) coming in W3-W4.
    result = verifier.verify(
        claim=request.claim,
        source_passage=(
            "(Source text not yet available. Upload a source paper first, "
            "then re-run verification. This is a placeholder response.)"
        ),
        client=llm_client,  # None = mock mode if no API key configured
    )

    return VerifyResponse(
        claim=result.claim,
        verdict=VerdictEnum(result.verdict.value),
        confidence=result.confidence,
        rationale=result.rationale,
        matches=[
            MatchResult(
                passage_text=result.source_text_used,
                similarity=0.0,
                entailment_label=VerdictEnum(result.verdict.value),
                confidence=result.confidence,
            )
        ],
    )
