"""Batch audit endpoints — verify all citations in a manuscript."""

from fastapi import APIRouter, HTTPException

from ..models import (
    AuditRequest,
    AuditResponse,
)

router = APIRouter()


@router.post("/audit", response_model=AuditResponse)
async def audit_manuscript(request: AuditRequest):
    """Run a full citation audit on a manuscript.

    Verifies every claim-citation pair in the manuscript against
    the uploaded source papers.

    Returns a risk-ranked report of all citations.
    """
    if not request.manuscript_id:
        raise HTTPException(status_code=400, detail="Manuscript ID is required.")
    if not request.source_paper_ids:
        raise HTTPException(status_code=400, detail="At least one source paper is required.")

    # TODO W5-W6: Real batch audit pipeline
    # 1. Extract claims + \cite{...} pairs from manuscript
    # 2. For each pair: retrieve + verify
    # 3. Aggregate results + assign risk levels

    return AuditResponse(
        manuscript_id=request.manuscript_id,
        total_citations=0,
        supported=0,
        partial=0,
        contradicted=0,
        not_found=0,
        results=[],
    )


@router.get("/audit/{audit_id}", response_model=AuditResponse)
async def get_audit_result(audit_id: str):
    """Get the results of a previously run audit.

    Args:
        audit_id: The audit ID returned by POST /api/audit.

    Returns:
        AuditResponse with all citation results.
    """
    # TODO W6: Retrieve from audit result store
    raise HTTPException(status_code=404, detail="Audit not found (not yet implemented).")
