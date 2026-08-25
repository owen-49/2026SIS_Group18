"""Shared Pydantic models for the API."""

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class VerdictEnum(str, Enum):
    SUPPORT = "SUPPORT"
    PARTIAL = "PARTIAL"
    CONTRADICT = "CONTRADICT"
    NOT_FOUND = "NOT_FOUND"


class ParseStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class BibFieldStatusEnum(str, Enum):
    MATCH = "MATCH"
    MISMATCH = "MISMATCH"
    PDF_MISSING = "PDF_MISSING"
    BIB_MISSING = "BIB_MISSING"
    NOT_CHECKED = "NOT_CHECKED"


# ── Request models ────────────────────────────────────────────


class VerifyRequest(BaseModel):
    claim: str = Field(..., description="The claim text to verify")
    source_paper_id: str = Field(
        ..., description="ID of the uploaded source paper to check against"
    )


class AuditRequest(BaseModel):
    manuscript_id: str = Field(..., description="ID of the uploaded manuscript")
    source_paper_ids: list[str] = Field(
        ..., description="IDs of all source papers cited in the manuscript"
    )


class BibVerifyRequest(BaseModel):
    bib_paper_id: str = Field(
        ..., description="ID of the uploaded .bib file (from /api/parse)"
    )
    source_paper_ids: list[str] = Field(
        default_factory=list,
        description="IDs of uploaded source PDFs to cross-check against",
    )




class PaperRecord(BaseModel):
    """Metadata persisted for an uploaded PDF or BibTeX file."""

    paper_id: str
    original_filename: str
    stored_filename: str
    file_path: str
    file_type: Literal["pdf", "bib"]
    file_size: int = Field(..., ge=0)
    status: ParseStatus = ParseStatus.PENDING
    pages: int = Field(default=0, ge=0)
    paragraph_count: int = Field(default=0, ge=0)
    entry_count: int = Field(default=0, ge=0)
    title: str | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class ParseResponse(BaseModel):
    paper_id: str
    status: ParseStatus
    file_type: str = "pdf"  # "pdf" | "bib"
    pages: int = 0
    paragraph_count: int = 0
    entry_count: int = 0  # number of bib entries parsed
    title: str | None = None


class PaperListItem(BaseModel):
    """Public metadata returned when listing uploaded papers."""

    paper_id: str
    original_filename: str
    file_type: Literal["pdf", "bib"]
    file_size: int = Field(..., ge=0)
    status: ParseStatus
    pages: int = Field(default=0, ge=0)
    paragraph_count: int = Field(default=0, ge=0)
    entry_count: int = Field(default=0, ge=0)
    title: str | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class PaperListResponse(BaseModel):
    """Collection of uploaded papers ordered from newest to oldest."""

    total: int = Field(..., ge=0)
    papers: list[PaperListItem] = Field(default_factory=list)


class MatchResult(BaseModel):
    passage_text: str
    similarity: float = Field(..., ge=0.0, le=1.0)
    entailment_label: VerdictEnum
    confidence: float = Field(..., ge=0.0, le=1.0)


class VerifyResponse(BaseModel):
    claim: str
    verdict: VerdictEnum
    confidence: float
    rationale: str
    matches: list[MatchResult] = []


class CitationAuditResult(BaseModel):
    citation_key: str
    claim: str
    verdict: VerdictEnum
    confidence: float
    risk_level: str  # "high", "medium", "low"


class AuditResponse(BaseModel):
    manuscript_id: str
    total_citations: int
    supported: int = 0
    partial: int = 0
    contradicted: int = 0
    not_found: int = 0
    results: list[CitationAuditResult] = []


# ── Bib verification models ───────────────────────────────────


class BibFieldResult(BaseModel):
    field_name: str
    bib_value: str
    pdf_value: str
    status: BibFieldStatusEnum
    detail: str = ""


class BibEntryVerificationResult(BaseModel):
    citation_key: str
    has_errors: bool
    error_count: int
    warning_count: int
    summary: str
    fields: list[BibFieldResult] = []


class BibVerifyResponse(BaseModel):
    bib_paper_id: str
    total_entries: int
    matched_entries: int
    error_entries: int
    results: list[BibEntryVerificationResult] = []


class ErrorResponse(BaseModel):
    detail: str
    error_code: str | None = None
