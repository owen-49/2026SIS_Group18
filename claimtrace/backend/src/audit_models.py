"""Bibliography Audit contracts, separate from single-claim Verify verdicts."""

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl, model_validator

from .models import BibEntryRecord


class AuditStatus(str, Enum):
    VERIFIED = "VERIFIED"
    METADATA_MISMATCH = "METADATA_MISMATCH"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    NOT_FOUND = "NOT_FOUND"
    LOOKUP_FAILED = "LOOKUP_FAILED"


class ReferenceEntry(BaseModel):
    entry_id: str
    metadata: BibEntryRecord
    number: int | None = None
    page_start: int | None = None
    page_end: int | None = None


class BibliographicMetadata(BaseModel):
    title: str = ""
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    venue: str = ""
    doi: str = ""


class ExternalRecord(BaseModel):
    """A record retrieved by the lookup adapter, never an uploaded PDF."""

    provider: str = Field(min_length=1)
    record_id: str = Field(min_length=1)
    url: HttpUrl
    retrieved_at: datetime
    metadata: BibliographicMetadata


class LookupAttempt(BaseModel):
    provider: str
    outcome: Literal["found", "ambiguous", "not_found", "failed"]
    error_code: str | None = None
    detail: str = ""


class LookupResult(BaseModel):
    """Adapter decides identity; backend compares fields of an identified record.

    not_found means all configured lookup paths completed without an acceptable
    candidate. Exhausted retries or incomplete lookup paths must return failed.
    """

    outcome: Literal["found", "ambiguous", "not_found", "failed"]
    records: list[ExternalRecord] = Field(default_factory=list)
    attempts: list[LookupAttempt] = Field(min_length=1)
    reason: str

    @model_validator(mode="after")
    def validate_outcome(self):
        if self.outcome == "found" and len(self.records) != 1:
            raise ValueError("An identified publication requires exactly one external record.")
        if self.outcome == "not_found" and (
            self.records or any(attempt.outcome != "not_found" for attempt in self.attempts)
        ):
            raise ValueError("Not found requires completed, negative lookup attempts.")
        if self.outcome == "ambiguous" and not self.records:
            raise ValueError("Ambiguous lookup requires candidates.")
        return self


class AuditFieldCheck(BaseModel):
    field_name: str
    input_value: str
    source_value: str
    status: Literal["MATCH", "MISMATCH", "INPUT_MISSING", "SOURCE_MISSING", "NOT_CHECKED"]
    detail: str = ""


class ReferenceAuditResult(BaseModel):
    entry: ReferenceEntry
    status: AuditStatus
    reason: str
    field_checks: list[AuditFieldCheck] = Field(default_factory=list)
    matched_record: ExternalRecord | None = None
    candidates: list[ExternalRecord] = Field(default_factory=list)
    lookup_attempts: list[LookupAttempt] = Field(default_factory=list)


class BibliographyAuditResponse(BaseModel):
    contract_version: Literal[2] = 2
    audit_id: str
    input_paper_id: str
    input_type: Literal["bib", "pdf"]
    checked_at: datetime
    status: Literal["completed", "completed_with_errors", "needs_review"]
    total_entries: int
    counts: dict[AuditStatus, int]
    results: list[ReferenceAuditResult]
    warnings: list[str] = Field(default_factory=list)
