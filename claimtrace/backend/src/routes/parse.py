"""PDF upload and parsing endpoints."""

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
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")

    paper_id = str(uuid.uuid4())[:8]

    # Save uploaded file
    file_path = UPLOAD_DIR / f"{paper_id}.pdf"
    content = await file.read()
    if len(content) > 50 * 1024 * 1024:  # 50MB limit
        raise HTTPException(status_code=400, detail="File too large (max 50MB).")

    file_path.write_bytes(content)

    # TODO W2-W3: Call parser.pdf_parser.parse_pdf() and element extractors
    # For now, return stub with placeholder values

    _paper_store[paper_id] = {
        "file_path": str(file_path),
        "status": ParseStatus.PENDING,
    }

    return ParseResponse(
        paper_id=paper_id,
        status=ParseStatus.PENDING,
        pages=0,
        paragraph_count=0,
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
        pages=paper.get("pages", 0),
        paragraph_count=paper.get("paragraph_count", 0),
        title=paper.get("title"),
    )
