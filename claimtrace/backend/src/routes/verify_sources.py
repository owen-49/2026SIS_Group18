"""Verify-only source PDF upload and selection endpoints."""

from fastapi import APIRouter, File, HTTPException, UploadFile

from ..config import get_settings
from ..models import PaperListItem, PaperListResponse, PaperScope, ParseResponse
from ..storage.paper_store import PaperStoreError, list_papers
from .parse import _persist_upload

router = APIRouter()

settings = get_settings()
SOURCE_UPLOAD_DIR = settings.upload_dir / "verify-sources"
_INTERNAL_FIELDS = {"stored_filename", "file_path", "parsed_result_path"}


@router.post("/verify/sources", response_model=ParseResponse)
async def upload_verify_source(file: UploadFile = File(...)):
    """Upload a PDF that can only be selected for claim comparison."""
    return await _persist_upload(
        file,
        upload_dir=SOURCE_UPLOAD_DIR,
        scope=PaperScope.VERIFY_SOURCE,
        pdf_only=True,
    )


@router.get("/verify/sources", response_model=PaperListResponse)
def list_verify_sources():
    """List PDFs uploaded for the Verify claim comparison workflow."""
    try:
        records = [
            record
            for record in list_papers()
            if record.scope is PaperScope.VERIFY_SOURCE and record.file_type == "pdf"
        ]
    except PaperStoreError as exc:
        raise HTTPException(status_code=500, detail="Unable to read source PDF metadata.") from exc

    papers = [
        PaperListItem.model_validate(record.model_dump(exclude=_INTERNAL_FIELDS))
        for record in records
    ]
    return PaperListResponse(total=len(papers), papers=papers)
