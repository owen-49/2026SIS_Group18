"""Bibliography existence/metadata Audit, independent of claim-support Verify."""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request

from ..audit_models import BibliographyAuditResponse
from ..models import AuditRequest
from ..services.bibliography_audit_service import run_bibliography_audit
from ..services.bibliography_lookup import BibliographyLookup
from ..services.paper_lifecycle import paper_lifecycle_lock
from ..services.reference_input_service import AuditInputError
from ..storage.audit_store import load_audit, save_audit

router = APIRouter()
logger = logging.getLogger(__name__)


def get_bibliography_lookup(request: Request) -> BibliographyLookup | None:
    """Integration hook for the external lookup team's implementation."""
    return getattr(request.app.state, "bibliography_lookup", None)


@router.post("/audit", response_model=BibliographyAuditResponse)
def audit_bibliography(request: AuditRequest, lookup=Depends(get_bibliography_lookup)):
    # FastAPI runs sync handlers in its worker pool, keeping blocking Parser
    # calls (and future bounded external queries) off the event loop.
    try:
        paper_id = request.bib_paper_id or request.manuscript_id
        if paper_id is None:  # The request model normally rejects this before routing.
            raise AuditInputError(422, "INPUT_REQUIRED", "An audit input is required.")
        with paper_lifecycle_lock(paper_id):
            report = run_bibliography_audit(request, lookup)
            save_audit(report)
        return report
    except AuditInputError as exc:
        if exc.status_code >= 500:
            logger.exception("Unable to prepare bibliography input")
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    except OSError as exc:
        logger.exception("Unable to save bibliography audit")
        raise HTTPException(
            status_code=500,
            detail={
                "code": "AUDIT_STORAGE_FAILED",
                "message": "Unable to save the audit report.",
            },
        ) from exc


@router.get("/audit/{audit_id}", response_model=BibliographyAuditResponse)
def get_audit_result(audit_id: UUID):
    try:
        return load_audit(audit_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Audit not found.") from exc
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=500, detail="Unable to read the audit report.") from exc
