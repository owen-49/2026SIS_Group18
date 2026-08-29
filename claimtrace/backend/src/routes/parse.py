"""PDF and BibTeX (.bib) upload and parsing endpoints."""

import uuid
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

from ..config import get_settings
from ..models import PaperRecord, ParseResponse
from ..services.bib_service import (
    BibProcessingError,
    InvalidBibPaperError,
    process_uploaded_bib,
)
from ..services.pipeline_service import PipelineError, process_uploaded_paper
from ..storage.paper_store import PaperStoreError, create_paper, get_paper

router = APIRouter()

settings = get_settings()
UPLOAD_DIR = settings.upload_dir
MAX_UPLOAD_SIZE_BYTES = settings.max_upload_size_mb * 1024 * 1024
UPLOAD_CHUNK_SIZE = 1024 * 1024
SUPPORTED_FILE_TYPES = {"pdf", "bib"}


def _validate_filename(filename: str | None) -> tuple[str, str]:
    """Validate an upload name and return the clean name and extension."""
    if filename is None:
        raise HTTPException(status_code=400, detail="No file provided.")

    clean_name = filename.strip()
    if (
        not clean_name
        or clean_name in {".", ".."}
        or "/" in clean_name
        or "\\" in clean_name
        or any(ord(character) < 32 for character in clean_name)
    ):
        raise HTTPException(status_code=400, detail="Invalid file name.")

    extension = Path(clean_name).suffix.lower().lstrip(".")
    if extension not in SUPPORTED_FILE_TYPES:
        display_extension = f".{extension}" if extension else ""
        raise HTTPException(
            status_code=415,
            detail=(
                f"Unsupported file type '{display_extension}'. "
                "Only PDF and .bib files are accepted."
            ),
        )

    return clean_name, extension


async def _write_upload_to_temporary_file(
    upload: UploadFile,
    temporary_path: Path,
) -> tuple[int, bytes]:
    """Stream an upload to disk while enforcing the configured size limit."""
    file_size = 0
    header = b""

    with temporary_path.open("xb") as destination:
        while chunk := await upload.read(UPLOAD_CHUNK_SIZE):
            file_size += len(chunk)
            if file_size > MAX_UPLOAD_SIZE_BYTES:
                raise HTTPException(
                    status_code=413,
                    detail=f"File too large (max {settings.max_upload_size_mb}MB).",
                )

            if len(header) < 4:
                header += chunk[: 4 - len(header)]
            destination.write(chunk)

    return file_size, header


def _to_parse_response(record: PaperRecord) -> ParseResponse:
    return ParseResponse(
        paper_id=record.paper_id,
        status=record.status,
        file_type=record.file_type,
        pages=record.pages,
        paragraph_count=record.paragraph_count,
        entry_count=record.entry_count,
        title=record.title,
    )


@router.post("/parse", response_model=ParseResponse)
async def parse_pdf(file: UploadFile = File(...)):
    """Validate and persist an uploaded PDF or BibTeX file."""
    original_filename, file_type = _validate_filename(file.filename)
    paper_id = str(uuid.uuid4())
    stored_filename = f"{paper_id}.{file_type}"

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    temporary_dir = UPLOAD_DIR / ".tmp"
    temporary_dir.mkdir(parents=True, exist_ok=True)
    temporary_path = temporary_dir / f"{paper_id}.part"
    final_path = UPLOAD_DIR / stored_filename

    try:
        file_size, header = await _write_upload_to_temporary_file(file, temporary_path)
        if file_size == 0:
            raise HTTPException(status_code=400, detail="The uploaded file is empty.")
        if file_type == "pdf" and not header.startswith(b"%PDF"):
            raise HTTPException(status_code=415, detail="The uploaded file is not a valid PDF.")

        temporary_path.replace(final_path)
        timestamp = datetime.now(UTC)
        record = PaperRecord(
            paper_id=paper_id,
            original_filename=original_filename,
            stored_filename=stored_filename,
            file_path=str(final_path),
            file_type=file_type,
            file_size=file_size,
            title=Path(original_filename).stem,
            created_at=timestamp,
            updated_at=timestamp,
        )

        try:
            create_paper(record)
        except PaperStoreError as exc:
            final_path.unlink(missing_ok=True)
            raise HTTPException(
                status_code=500,
                detail="Unable to persist paper metadata.",
            ) from exc

        if record.file_type == "pdf":
            try:
                record = process_uploaded_paper(record.paper_id)
            except PipelineError as exc:
                raise HTTPException(
                    status_code=500,
                    detail="Unable to process the uploaded PDF.",
                ) from exc
        else:
            try:
                record = process_uploaded_bib(record.paper_id)
            except InvalidBibPaperError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            except BibProcessingError as exc:
                raise HTTPException(
                    status_code=500,
                    detail="Unable to process the uploaded BibTeX file.",
                ) from exc

        return _to_parse_response(record)
    except HTTPException:
        temporary_path.unlink(missing_ok=True)
        raise
    except OSError as exc:
        temporary_path.unlink(missing_ok=True)
        final_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail="Unable to save the uploaded file.") from exc
    finally:
        await file.close()


@router.get("/parse/{paper_id}", response_model=ParseResponse)
async def get_parse_status(paper_id: str):
    """Return persisted metadata for a previously uploaded paper."""
    try:
        paper = get_paper(paper_id)
    except PaperStoreError as exc:
        raise HTTPException(status_code=500, detail="Unable to read paper metadata.") from exc

    if paper is None:
        raise HTTPException(status_code=404, detail="Paper not found.")

    return _to_parse_response(paper)
