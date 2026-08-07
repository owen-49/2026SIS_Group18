"""Shared Pydantic models for the API."""

from enum import Enum

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


# ── Response models ───────────────────────────────────────────


class ParseResponse(BaseModel):
    paper_id: str
    status: ParseStatus
    pages: int = 0
    paragraph_count: int = 0
    title: str | None = None


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


class ErrorResponse(BaseModel):
    detail: str
    error_code: str | None = None
