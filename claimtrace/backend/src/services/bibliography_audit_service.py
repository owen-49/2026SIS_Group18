"""Bibliographic identity and metadata orchestration; never claim entailment."""

import logging
import re
import unicodedata
from datetime import UTC, datetime
from uuid import uuid4

from engine.bib_parser import BibEntry
from engine.bib_verifier import PdfMetadata, verify_bib_against_pdf

from ..audit_models import (
    AuditFieldCheck,
    AuditStatus,
    BibliographyAuditResponse,
    ExternalRecord,
    LookupAttempt,
    LookupResult,
    ReferenceAuditResult,
    ReferenceEntry,
)
from ..models import AuditRequest
from .bibliography_lookup import BibliographyLookup
from .reference_input_service import load_audit_references

logger = logging.getLogger(__name__)


def _normalise(value: str) -> str:
    return re.sub(r"[\W_]+", " ", unicodedata.normalize("NFKC", value).casefold()).strip()


def compare_external_metadata(
    entry: ReferenceEntry,
    record: ExternalRecord,
) -> tuple[AuditStatus, list[AuditFieldCheck], str]:
    """Adapt the Engine's metadata comparator; no PDF is loaded or required.

    PdfMetadata is the existing Engine value object. Its PDF-specific statuses
    are translated to external-record terminology. Fuzzy matches need review.
    """
    source = record.metadata
    compared = verify_bib_against_pdf(
        BibEntry(**entry.metadata.model_dump()),
        PdfMetadata(**source.model_dump()),
    )
    status_map = {"PDF_MISSING": "SOURCE_MISSING", "BIB_MISSING": "INPUT_MISSING"}
    details = {
        "MATCH": "The existing Engine metadata comparator reports a match.",
        "MISMATCH": "The reference field differs from the retrieved external record.",
        "INPUT_MISSING": "This field is missing from the input reference.",
        "SOURCE_MISSING": "This field is missing from the external record.",
        "NOT_CHECKED": "This optional field was not checked.",
    }
    checks = []
    for result in compared.fields:
        status = status_map.get(result.status.value, result.status.value)
        checks.append(
            AuditFieldCheck(
                field_name=result.field_name,
                input_value=result.bib_value,
                source_value=result.pdf_value,
                status=status,
                detail=details[status],
            )
        )
    for field in ("venue", "doi"):
        if not any(check.field_name == field for check in checks):
            checks.append(
                AuditFieldCheck(
                    field_name=field,
                    input_value="",
                    source_value="",
                    status="NOT_CHECKED",
                    detail="Neither input nor external record supplies this field.",
                )
            )
    if any(check.status == "MISMATCH" for check in checks):
        return AuditStatus.METADATA_MISMATCH, checks, "Identified record has field differences."
    required = {"title", "authors", "year", "venue"}
    complete = all(check.status == "MATCH" for check in checks if check.field_name in required)
    # Engine accepts some surname-only/partial-string matches. Keep its field
    # results, but do not report those as fully verified metadata.
    exact = (
        _normalise(entry.metadata.title) == _normalise(source.title)
        and [_normalise(name) for name in entry.metadata.authors]
        == [_normalise(name) for name in source.authors]
        and _normalise(entry.metadata.venue) == _normalise(source.venue)
    )
    if complete and exact:
        return AuditStatus.VERIFIED, checks, "External record identified; required metadata agrees."
    return (
        AuditStatus.NEEDS_REVIEW,
        checks,
        "External record found, but missing fields or fuzzy metadata agreement need human review.",
    )


def audit_reference(
    entry: ReferenceEntry, lookup: BibliographyLookup | None
) -> ReferenceAuditResult:
    if lookup is None:
        return ReferenceAuditResult(
            entry=entry,
            status=AuditStatus.LOOKUP_FAILED,
            reason="External lookup is not integrated. Publication existence is unchecked.",
            lookup_attempts=[
                LookupAttempt(
                    provider="unconfigured",
                    outcome="failed",
                    error_code="EXTERNAL_LOOKUP_NOT_CONFIGURED",
                    detail="No DOI/database lookup implementation is available in this repository.",
                )
            ],
        )
    try:
        result = LookupResult.model_validate(lookup.lookup(entry))
        if result.outcome == "found":
            record = result.records[0]
            status, checks, reason = compare_external_metadata(entry, record)
            return ReferenceAuditResult(
                entry=entry,
                status=status,
                reason=reason,
                field_checks=checks,
                matched_record=record,
                lookup_attempts=result.attempts,
            )
        status = {
            "ambiguous": AuditStatus.NEEDS_REVIEW,
            "not_found": AuditStatus.NOT_FOUND,
            "failed": AuditStatus.LOOKUP_FAILED,
        }[result.outcome]
        reason = result.reason
        if status == AuditStatus.NOT_FOUND:
            reason += (
                " No acceptable record in the queried sources; this does not prove fabrication."
            )
        return ReferenceAuditResult(
            entry=entry,
            status=status,
            reason=reason,
            candidates=result.records,
            lookup_attempts=result.attempts,
        )
    except Exception:
        logger.exception("Lookup/comparison failed for %s", entry.entry_id)
        return ReferenceAuditResult(
            entry=entry,
            status=AuditStatus.LOOKUP_FAILED,
            reason="Lookup failed or returned an invalid result; existence is unchecked.",
            lookup_attempts=[
                LookupAttempt(
                    provider="configured_adapter",
                    outcome="failed",
                    error_code="LOOKUP_ADAPTER_FAILED",
                )
            ],
        )


def run_bibliography_audit(
    request: AuditRequest,
    lookup: BibliographyLookup | None,
) -> BibliographyAuditResponse:
    paper_id, input_type, entries, warnings = load_audit_references(request)
    results = [audit_reference(entry, lookup) for entry in entries]
    counts = {status: sum(result.status == status for result in results) for status in AuditStatus}
    status = "completed_with_errors" if counts[AuditStatus.LOOKUP_FAILED] else "completed"
    if not entries:
        status = "needs_review"
    return BibliographyAuditResponse(
        audit_id=str(uuid4()),
        input_paper_id=paper_id,
        input_type=input_type,
        checked_at=datetime.now(UTC),
        status=status,
        total_entries=len(entries),
        counts=counts,
        results=results,
        warnings=warnings,
    )
