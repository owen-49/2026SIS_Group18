"""Endpoints for listing persisted paper metadata."""

from fastapi import APIRouter, HTTPException

from ..models import PaperListItem, PaperListResponse
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
