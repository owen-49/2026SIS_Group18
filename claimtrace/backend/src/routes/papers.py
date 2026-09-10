"""Endpoints for listing persisted paper metadata."""

from fastapi import APIRouter, HTTPException, Response, status
from fastapi.responses import JSONResponse

from ..models import PaperClaimsResponse, PaperListItem, PaperListResponse
from ..services.analysis_service import (
    AnalysisPaperNotFoundError,
    AnalysisServiceError,
    InvalidAnalysisPaperError,
    get_paper_claims,
)
from ..services.paper_deletion_service import (
    PaperDeletionError,
    PaperDeletionNotFoundError,
    PaperDeletionOutcome,
    delete_uploaded_paper,
)
from ..storage.paper_store import PaperStoreError, list_papers

router = APIRouter()

_INTERNAL_FIELDS = {"stored_filename", "file_path", "parsed_result_path"}


@router.get("/papers", response_model=PaperListResponse)
async def get_papers():
    """Return uploaded papers ordered from newest to oldest."""
    try:
        records = list_papers()
    except PaperStoreError as exc:
        raise HTTPException(status_code=500, detail="Unable to read paper metadata.") from exc

    papers = [
        PaperListItem.model_validate(record.model_dump(exclude=_INTERNAL_FIELDS))
        for record in records
    ]
    return PaperListResponse(total=len(papers), papers=papers)


@router.delete("/papers/{paper_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_paper(paper_id: str) -> Response:
    """Delete one uploaded paper and all of its local artifacts."""
    try:
        outcome = delete_uploaded_paper(paper_id)
    except PaperDeletionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PaperDeletionError as exc:
        raise HTTPException(
            status_code=500,
            detail="Unable to delete the paper and its local artifacts.",
        ) from exc
    if outcome == PaperDeletionOutcome.CLEANUP_PENDING:
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={"paper_id": paper_id, "status": "cleanup_pending"},
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/papers/{paper_id}/claims", response_model=PaperClaimsResponse)
async def get_claims(paper_id: str):
    """Extract citation-bearing claims from a persisted manuscript."""
    try:
        return get_paper_claims(paper_id)
    except AnalysisPaperNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidAnalysisPaperError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except AnalysisServiceError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
