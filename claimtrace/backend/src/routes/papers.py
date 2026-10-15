"""Endpoints for listing persisted paper metadata."""

import mimetypes
from pathlib import Path

from fastapi import APIRouter, HTTPException, Response, status
from fastapi.responses import FileResponse, JSONResponse

from ..models import (
    PaperClaimsResponse,
    PaperListItem,
    PaperListResponse,
    PaperMarkdownResponse,
    PaperScope,
)
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
from ..storage.paper_store import PaperStoreError, get_paper, list_papers

router = APIRouter()

_INTERNAL_FIELDS = {"stored_filename", "file_path", "parsed_result_path"}


@router.get("/papers", response_model=PaperListResponse)
async def get_papers():
    """Return uploaded papers ordered from newest to oldest."""
    try:
        records = [record for record in list_papers() if record.scope is PaperScope.LIBRARY]
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
def get_claims(paper_id: str, bib_paper_id: str | None = None):
    """Extract citation-bearing claims from a persisted manuscript."""
    try:
        return get_paper_claims(paper_id, bib_paper_id=bib_paper_id)
    except AnalysisPaperNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidAnalysisPaperError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except AnalysisServiceError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/papers/{paper_id}/markdown", response_model=PaperMarkdownResponse)
def get_markdown(paper_id: str):
    """Return the Parser's enhanced Markdown artifact for a paper."""
    record = get_paper(paper_id)
    if record is None or not record.parsed_result_path:
        raise HTTPException(status_code=404, detail="No parsed document for this paper.")
    markdown_path = (
        Path(record.parsed_result_path).parent / "markdown" / f"{paper_id}.md"
    )
    if not markdown_path.is_file():
        raise HTTPException(
            status_code=404, detail="Markdown is not available for this paper."
        )
    try:
        markdown = markdown_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise HTTPException(
            status_code=500, detail="Unable to read the Markdown artifact."
        ) from exc
    return PaperMarkdownResponse(paper_id=paper_id, markdown=markdown)


@router.get("/papers/{paper_id}/images/{filename}")
def get_paper_image(paper_id: str, filename: str):
    """Serve an image extracted from a parsed paper."""
    # Reject path separators so callers cannot escape the images directory.
    if not filename or Path(filename).name != filename:
        raise HTTPException(status_code=404, detail="Image not found.")
    record = get_paper(paper_id)
    if record is None or not record.parsed_result_path:
        raise HTTPException(status_code=404, detail="Image not found.")
    image_path = (
        Path(record.parsed_result_path).parent / "markdown" / f"{paper_id}_images" / filename
    )
    if not image_path.is_file():
        raise HTTPException(status_code=404, detail="Image not found.")
    media_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    return FileResponse(image_path, media_type=media_type)
