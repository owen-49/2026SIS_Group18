"""Bibliographic identity and metadata orchestration; never claim entailment."""

import logging
import re
import unicodedata
from datetime import UTC, datetime
from uuid import uuid4

from engine.bib_parser import BibEntry, author_surnames
from engine.bib_verifier import PdfMetadata, verify_bib_against_pdf
from engine.identity import ReferenceQuery

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
from .reference_query import reference_query_for

logger = logging.getLogger(__name__)


def _normalise(value: str) -> str:
    return re.sub(r"[\W_]+", " ", unicodedata.normalize("NFKC", value).casefold()).strip()


def _folded(value: str) -> str:
    """``_normalise`` with accents folded away.

    Deliberately separate from :func:`_normalise`, because the two answer
    different questions. A title or a venue is compared as each source wrote it,
    and folding those would move that comparison without a measurement asking for
    it. An author's name is compared for identity, and there "Tomáš Mikolov" and
    "Tomas Mikolov" are one person that two sources spell differently.
    """
    decomposed = unicodedata.normalize("NFKD", value or "")
    return _normalise("".join(char for char in decomposed if not unicodedata.combining(char)))


def _author_reading(name: str) -> tuple[str, tuple[str, ...]]:
    """Return one author as ``(surname, the given names the name states)``.

    Goes through :func:`engine.bib_parser.author_surnames` so both name orders
    read the same: "Bastian Epping" and "Epping, Bastian" are one reading. Single
    letters are dropped, because an initial is a source abbreviating a name
    rather than stating one, and keeping them would refuse "Michael T. Schaub"
    against "Schaub, Michael".

    A multi-word surname is only read whole in the "Last, First" order, so "van
    der Berg" does not pair with "Berg, van der". No entry in the stored corpus
    has one, and a rule for them would be a rule nothing measured.
    """
    surname = _folded(author_surnames([name])[0])
    remaining = _folded(name).split()
    for token in surname.split():
        if token in remaining:
            remaining.remove(token)
    return surname, tuple(sorted({token for token in remaining if len(token) > 1}))


def _authors_agree(left: list[str], right: list[str]) -> bool:
    """Whether two author lists name the same people.

    Not differences: the order the names are listed in, the order within a name,
    middle initials, and accents -- each is how a source happens to spell a name.
    Differences: the names both sides state. "Smith, Jane" against "Smith, John"
    shares a surname and is not the same person.

    A name one side abbreviates cannot contradict, which is the asymmetry that
    makes this usable on real references: "Vaswani, A." is never refused against
    "Vaswani, Ashish", because the reference stated no given name to disagree
    with.
    """
    if not left or len(left) != len(right):
        return False
    readings = [_author_reading(name) for name in left]
    unmatched = [_author_reading(name) for name in right]
    if sorted(surname for surname, _ in readings) != sorted(
        surname for surname, _ in unmatched
    ):
        return False
    for surname, given in readings:
        for index, (other_surname, other_given) in enumerate(unmatched):
            if other_surname != surname:
                continue
            if given and other_given and given != other_given:
                continue
            unmatched.pop(index)
            break
        else:
            return False
    return True


def _recovered_fields(entry: ReferenceEntry, query: ReferenceQuery) -> dict[str, bool]:
    """Which compared fields came from the reference's raw text, not its metadata.

    For a reference read from a PDF reference list this is most of them: measured
    over the 174 stored entries, the structured title is non-empty for one and the
    raw text supplies one for 173. For a BibTeX entry nothing is ever recovered --
    ``reference_query_for`` does not parse an ``@article{...}`` block as a
    reference-list entry, and its structured fields are complete by construction.
    """
    metadata = entry.metadata
    return {
        "title": not (metadata.title or "").strip() and bool(query.title),
        "authors": not metadata.authors and bool(query.authors),
        "year": metadata.year is None and query.year is not None,
        "venue": not (metadata.venue or "").strip() and bool(query.venue),
        "doi": not (metadata.doi or "").strip() and bool(query.doi),
    }


def compare_external_metadata(
    entry: ReferenceEntry,
    record: ExternalRecord,
) -> tuple[AuditStatus, list[AuditFieldCheck], str]:
    """Adapt the Engine's metadata comparator; no PDF is loaded or required.

    Compares the record against the reference's *searchable* description -- the
    query the lookup was handed, from ``reference_query_for`` -- rather than
    against its stored structured fields. For a reference read from a PDF
    reference list those are empty, so comparing them asked whether the record
    agreed with fields the reference never carried: every check came back
    ``INPUT_MISSING`` and a record the lookup had found could not reach a verdict.
    One description of the reference, read by the guard, the lookup and this
    comparison alike.

    PdfMetadata is the existing Engine value object. Its PDF-specific statuses
    are translated to external-record terminology. Fuzzy matches need review.
    """
    source = record.metadata
    query = reference_query_for(entry)
    recovered = _recovered_fields(entry, query)
    metadata = entry.metadata
    compared = verify_bib_against_pdf(
        BibEntry(
            key=metadata.key,
            entry_type=metadata.entry_type,
            title=query.title,
            authors=list(query.authors),
            year=query.year,
            venue=query.venue,
            doi=query.doi,
            raw_text=metadata.raw_text,
        ),
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
    recovered_details = {
        "MATCH": "Recovered from the reference's raw text; it agrees with the external record.",
        "MISMATCH": "Recovered from the reference's raw text, and it differs from the external "
        "record. The difference may be in the extraction rather than in the reference.",
        "SOURCE_MISSING": "Recovered from the reference's raw text; the external record does "
        "not carry this field.",
    }
    checks = []
    for result in compared.fields:
        status = status_map.get(result.status.value, result.status.value)
        detail = details[status]
        if recovered.get(result.field_name):
            detail = recovered_details.get(status, detail)
        checks.append(
            AuditFieldCheck(
                field_name=result.field_name,
                input_value=result.bib_value,
                source_value=result.pdf_value,
                status=status,
                detail=detail,
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
    # A difference in a value the reference's own metadata states is a difference
    # in the reference. A difference in a value recovered from its raw text may be
    # the extraction's, so it can withhold VERIFIED but must not assert the
    # reference is wrong: measured over the 91 stored matched records, venue
    # differs in 50 of them and nearly every one is the reference abbreviating a
    # venue the record spells out, as "ACL" against the full proceedings name.
    if any(
        check.status == "MISMATCH" and not recovered.get(check.field_name) for check in checks
    ):
        return AuditStatus.METADATA_MISMATCH, checks, "Identified record has field differences."
    required = {"title", "authors", "year", "venue"}
    complete = all(check.status == "MATCH" for check in checks if check.field_name in required)
    # Engine accepts some surname-only/partial-string matches, and its author rule
    # reads surnames alone. Keep its field results, but do not report those as
    # fully verified metadata: the author clause below also compares the given
    # names both sides state, so a shared surname is not on its own agreement.
    exact = (
        _normalise(query.title) == _normalise(source.title)
        and _authors_agree(list(query.authors), list(source.authors))
        and _normalise(query.venue) == _normalise(source.venue)
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
    # The searchable title, not the stored one. A reference-list entry from a
    # PDF carries its title in the raw text -- measured over the 174 entries
    # under uploads/parsed, the structured field holds a title for exactly one
    # of them, while the raw text yields one for 173. Guarding on the stored
    # field therefore returned every PDF reference here before any lookup ran.
    # The lookup resolves the same question through the same function, so the
    # two cannot drift into disagreeing about what is searchable.
    if not reference_query_for(entry).title.strip():
        return ReferenceAuditResult(
            entry=entry,
            status=AuditStatus.NEEDS_REVIEW,
            reason="No searchable title was extracted. Review the original reference; "
            "publication existence has not been checked.",
        )
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
