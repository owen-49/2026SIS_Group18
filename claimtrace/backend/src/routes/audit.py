"""Batch audit endpoints — verify all citations in a manuscript."""

from fastapi import APIRouter, HTTPException, Request

from ..models import (
    AuditRequest,
    AuditResponse,
)
from ..services.analysis_service import (
    AnalysisPaperNotFoundError,
    AnalysisPaperNotReadyError,
    AnalysisServiceError,
    InvalidAnalysisPaperError,
    run_audit,
)

router = APIRouter()


@router.post("/audit", response_model=AuditResponse)
async def audit_manuscript(request: AuditRequest, http_request: Request):
    """Run a full citation audit on a manuscript.

    Verifies every claim-citation pair in the manuscript against
    the uploaded source papers.

    Returns a risk-ranked report of all citations.
    """
    if not request.manuscript_id:
        raise HTTPException(status_code=400, detail="Manuscript ID is required.")
    if not request.source_paper_ids:
        raise HTTPException(status_code=400, detail="At least one source paper is required.")

    try:
        return run_audit(
            manuscript_id=request.manuscript_id.strip(),
            source_paper_ids=request.source_paper_ids,
            llm_client=getattr(http_request.app.state, "llm_client", None),
            llm_model=getattr(http_request.app.state, "llm_model", ""),
        )
    except AnalysisPaperNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except AnalysisPaperNotReadyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except InvalidAnalysisPaperError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except AnalysisServiceError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


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
