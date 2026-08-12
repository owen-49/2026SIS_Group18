"""PDF and BibTeX (.bib) upload and parsing endpoints."""

import uuid
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

from ..models import ParseResponse, ParseStatus

router = APIRouter()

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

# In-memory store for parsed papers (replace with DB in production)
_paper_store: dict[str, dict] = {}


@router.post("/parse", response_model=ParseResponse)
async def parse_pdf(file: UploadFile = File(...)):
    """Upload and parse an academic PDF.

    Args:
        file: PDF file upload (max 50MB).

    Returns:
        ParseResponse with paper ID and status.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided.")

    ext = file.filename.lower().rsplit(".", 1)[-1] if "." in file.filename else ""
    if ext not in ("pdf", "bib"):
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '.{ext}'. Only PDF and .bib files are accepted.",
        )

    paper_id = str(uuid.uuid4())[:8]
    file_type = ext  # "pdf" or "bib"

    # Save uploaded file
    file_path = UPLOAD_DIR / f"{paper_id}.{ext}"
    content = await file.read()
    if len(content) > 50 * 1024 * 1024:  # 50MB limit
        raise HTTPException(status_code=400, detail="File too large (max 50MB).")

    file_path.write_bytes(content)

    # Parse .bib files immediately (they're small text files)
    entry_count = 0
    if file_type == "bib":
        try:
            from engine.src.bib_parser import parse_bib_file
            entries = parse_bib_file(file_path)
            entry_count = len(entries)
        except Exception:
            entry_count = 0

    # TODO W2-W3: For PDFs, call parser.pdf_parser.parse_pdf() and element extractors
    # For now, return stub with placeholder values

    _paper_store[paper_id] = {
        "file_path": str(file_path),
        "file_type": file_type,
        "status": ParseStatus.COMPLETED if file_type == "bib" else ParseStatus.PENDING,
        "entry_count": entry_count,
    }

    return ParseResponse(
        paper_id=paper_id,
        status=ParseStatus.COMPLETED if file_type == "bib" else ParseStatus.PENDING,
        file_type=file_type,
        pages=0,
        paragraph_count=0,
        entry_count=entry_count,
    )


@router.get("/parse/{paper_id}", response_model=ParseResponse)
async def get_parse_status(paper_id: str):
    """Get the parsing status for a previously uploaded paper.

    Args:
        paper_id: The paper ID returned by POST /api/parse.

    Returns:
        Current ParseResponse with status.
    """
    if paper_id not in _paper_store:
        raise HTTPException(status_code=404, detail="Paper not found.")

    paper = _paper_store[paper_id]
    return ParseResponse(
        paper_id=paper_id,
        status=paper.get("status", ParseStatus.PENDING),
        file_type=paper.get("file_type", "pdf"),
        pages=paper.get("pages", 0),
        paragraph_count=paper.get("paragraph_count", 0),
        entry_count=paper.get("entry_count", 0),
        title=paper.get("title"),
    )
