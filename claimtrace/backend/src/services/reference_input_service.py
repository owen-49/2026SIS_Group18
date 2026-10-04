"""Consume existing Bib storage and the Parser team's reference-list extractor."""

from pathlib import Path
from threading import Lock
from uuid import NAMESPACE_URL, uuid5

from ..audit_models import ReferenceEntry
from ..models import AuditRequest, BibEntryRecord, PaperRecord, PaperScope, ParseStatus
from ..storage.bib_document_store import BibDocumentStoreError, load_bib_document
from ..storage.paper_store import PaperStoreError, get_paper
from ..storage.reference_store import (
    ReferenceStoreError,
    StoredReference,
    StoredReferenceList,
    load_references,
    save_references,
    source_digest,
)
from .reference_metadata_segmenter import (
    SegmentationOutcome,
    SegmentationStatus,
    segment_with_user_ai,
)

_REFERENCE_LOCKS = [Lock() for _ in range(32)]
_RETRYABLE_SEGMENTATION_STATUSES = {
    SegmentationStatus.NO_CLIENT.value,
    SegmentationStatus.MODEL_ERROR.value,
    SegmentationStatus.INVALID_RESPONSE.value,
}


class AuditInputError(RuntimeError):
    def __init__(self, status_code: int, code: str, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.code = code


def _entry_id(paper_id: str, index: int, text: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"claimtrace:{paper_id}:{index}:{text}"))


def extract_pdf_references(path: Path):
    """Call the existing Parser, preserving raw text rather than guessing fields."""
    try:
        from parser.reference_json_extractor import extract_references
    except ImportError as exc:
        raise AuditInputError(
            503, "REFERENCE_PARSER_UNAVAILABLE", "The reference Parser package is unavailable."
        ) from exc
    try:
        return extract_references(path)
    except Exception as exc:
        # Parser wraps missing OpenDataLoader/Java as conversion errors as well.
        raise AuditInputError(
            503,
            "REFERENCE_EXTRACTION_FAILED",
            "The existing reference Parser could not process the PDF. "
            "Check its OpenDataLoader/Java dependencies and backend logs.",
        ) from exc


def _has_structured_metadata(reference: StoredReference) -> bool:
    return bool(
        reference.title
        or reference.authors
        or reference.year is not None
        or reference.venue
        or reference.doi
    )


def _parser_metadata_complete(reference: StoredReference) -> bool:
    """Treat DOI and year as optional for otherwise complete APA/IEEE entries."""

    return bool(reference.title and reference.authors and reference.venue)


def _fallback_metadata_source(reference: StoredReference) -> str:
    return "parser" if _has_structured_metadata(reference) else "raw_text_heuristic"


def _apply_segmentation(
    reference: StoredReference,
    outcome: SegmentationOutcome,
) -> None:
    """Merge validated LLM fields into an incomplete Parser result."""

    reference.metadata_status = outcome.status.value
    reference.metadata_model = outcome.model
    reference.metadata_prompt_version = outcome.prompt_version

    if outcome.status in {SegmentationStatus.SEGMENTED, SegmentationStatus.PARTIAL}:
        metadata = outcome.metadata
        reference.title = metadata.title or reference.title
        reference.authors = metadata.authors or reference.authors
        reference.year = metadata.year if metadata.year is not None else reference.year
        reference.venue = metadata.venue or reference.venue
        reference.doi = metadata.doi or reference.doi
        reference.metadata_source = "llm_segmentation"
        return

    # Provider/configuration failures retain any safe Parser fields. The
    # downstream raw-text query fallback can still work when none were found.
    reference.metadata_source = _fallback_metadata_source(reference)


def _segment_stored_references(
    references: list[StoredReference], *, ai_runtime=None, retry_only=False
) -> None:
    pending = [
        reference
        for reference in references
        if not _parser_metadata_complete(reference)
        and (not retry_only or reference.metadata_status in _RETRYABLE_SEGMENTATION_STATUSES)
    ]
    for reference in references:
        if _parser_metadata_complete(reference) and reference.metadata_source is None:
            reference.metadata_source = "parser"
    if not pending:
        return

    raw = [reference.raw_text for reference in pending]
    outcomes = segment_with_user_ai(raw, ai_runtime=ai_runtime)
    for reference, outcome in zip(pending, outcomes, strict=True):
        _apply_segmentation(reference, outcome)


def _enrich_legacy_parser_metadata(saved: StoredReferenceList) -> None:
    """Apply the restored APA/IEEE Parser to pre-v2 raw-text artifacts."""

    if saved.metadata_version >= 2:
        return
    try:
        from parser.reference_json_extractor import parse_reference_metadata
    except ImportError as exc:
        raise AuditInputError(
            503,
            "REFERENCE_PARSER_UNAVAILABLE",
            "The reference Parser is required to enrich legacy references.",
        ) from exc
    for reference in saved.references:
        metadata = parse_reference_metadata(reference.raw_text)
        for name in ("title", "authors", "year", "venue", "doi"):
            if getattr(reference, name) in (None, []):
                setattr(reference, name, getattr(metadata, name))
    saved.metadata_version = 2


def _needs_llm_segmentation(saved: StoredReferenceList, *, ai_runtime=None) -> bool:
    if saved.metadata_version < 3:
        return True
    return (ai_runtime is not None) and any(
        not _parser_metadata_complete(reference)
        and reference.metadata_status in _RETRYABLE_SEGMENTATION_STATUSES
        for reference in saved.references
    )


def persisted_pdf_references(record: PaperRecord, *, ai_runtime=None) -> StoredReferenceList:
    """Reuse a valid artifact, extracting only when absent (one worker process)."""
    with _REFERENCE_LOCKS[hash(record.paper_id) % len(_REFERENCE_LOCKS)]:
        path = Path(record.file_path)
        try:
            saved = load_references(record.paper_id)
            if saved is not None:
                allowed_names = {path.name, record.original_filename, record.stored_filename}
                if Path(saved.source_file).name not in allowed_names:
                    raise ReferenceStoreError("Reference artifact source filename does not match.")
                if saved.source_sha256 and path.is_file():
                    if saved.source_sha256 != source_digest(path):
                        raise ReferenceStoreError("Reference artifact is stale; reprocess the PDF.")
                _enrich_legacy_parser_metadata(saved)
                if _needs_llm_segmentation(saved, ai_runtime=ai_runtime):
                    _segment_stored_references(
                        saved.references,
                        ai_runtime=ai_runtime,
                        retry_only=saved.metadata_version >= 3,
                    )
                    saved.metadata_version = 3
                    save_references(record.paper_id, saved)
                if ai_runtime is not None:
                    ai_runtime.raise_if_failed()
                return saved
            if not path.is_file():
                raise AuditInputError(
                    500, "INPUT_FILE_MISSING", "Uploaded manuscript PDF is missing."
                )
            digest = source_digest(path)
            extracted = extract_pdf_references(path)
            references = [
                StoredReference(
                    raw_text=reference.raw_text,
                    title=getattr(reference, "title", None),
                    authors=getattr(reference, "authors", None),
                    year=getattr(reference, "year", None),
                    venue=getattr(reference, "venue", None),
                    doi=getattr(reference, "doi", None),
                    number=reference.number,
                    page_start=reference.page_start,
                    page_end=reference.page_end,
                )
                for reference in extracted.references
            ]
            _segment_stored_references(references, ai_runtime=ai_runtime)
            saved = StoredReferenceList(
                metadata_version=3,
                source_file=path.name,
                paper_id=record.paper_id,
                source_sha256=digest,
                references=references,
                warnings=list(extracted.warnings),
            )
            save_references(record.paper_id, saved)
            if ai_runtime is not None:
                ai_runtime.raise_if_failed()
            return saved
        except (ReferenceStoreError, OSError, ValueError) as exc:
            raise AuditInputError(
                500,
                "REFERENCE_ARTIFACT_ERROR",
                "Reference JSON is invalid, stale, or unavailable for storage; reprocess the PDF "
                "or check backend logs. It was not silently re-extracted.",
            ) from exc


def load_audit_references(
    request: AuditRequest,
    *,
    ai_runtime=None,
) -> tuple[str, str, list[ReferenceEntry], list[str]]:
    paper_id = request.bib_paper_id or request.manuscript_id
    expected_type = "bib" if request.bib_paper_id else "pdf"
    try:
        record = get_paper(paper_id)
    except PaperStoreError as exc:
        raise AuditInputError(500, "STORAGE_ERROR", "Unable to read input metadata.") from exc
    if record is None:
        raise AuditInputError(404, "INPUT_NOT_FOUND", "Audit input was not found.")
    if record.file_type != expected_type:
        raise AuditInputError(422, "INPUT_TYPE_MISMATCH", f"Expected a {expected_type} upload.")
    if record.scope is PaperScope.VERIFY_SOURCE:
        raise AuditInputError(
            422,
            "INPUT_SCOPE_MISMATCH",
            "Verify-only source PDFs cannot be used as Audit inputs.",
        )
    if record.status != ParseStatus.COMPLETED:
        raise AuditInputError(409, "INPUT_NOT_READY", "The uploaded input is not ready.")

    warnings = []
    if request.source_paper_ids:
        warnings.append(
            "source_paper_ids is ignored: uploaded PDFs do not prove publication existence."
        )
    if expected_type == "bib":
        if not record.parsed_result_path:
            raise AuditInputError(500, "BIB_OUTPUT_MISSING", "Persisted Bib entries are missing.")
        try:
            document = load_bib_document(Path(record.parsed_result_path))
        except BibDocumentStoreError as exc:
            raise AuditInputError(500, "BIB_OUTPUT_INVALID", "Unable to read Bib entries.") from exc
        if document.paper_id != paper_id:
            raise AuditInputError(500, "BIB_ID_MISMATCH", "Persisted bibliography ID mismatch.")
        entries = [
            ReferenceEntry(
                entry_id=_entry_id(paper_id, index, entry.raw_text or entry.key),
                metadata=entry,
                metadata_source="bibtex",
            )
            for index, entry in enumerate(document.entries)
        ]
    else:
        references = persisted_pdf_references(record, ai_runtime=ai_runtime)
        warnings.extend(references.warnings)
        incomplete = sum(
            reference.metadata_status
            in {"NO_CLIENT", "MODEL_ERROR", "INVALID_RESPONSE", "VALIDATION_FAILED", "PARTIAL"}
            for reference in references.references
        )
        if incomplete:
            warnings.append(
                f"{incomplete} reference(s) have incomplete AI metadata extraction; "
                "Parser fields and original text remain available for review."
                + (
                    " Supply your own ai_config (provider, model and api_key)"
                    " to enable AI extraction."
                    if any(ref.metadata_status == "NO_CLIENT" for ref in references.references)
                    else ""
                )
            )
        entries = [
            ReferenceEntry(
                entry_id=_entry_id(paper_id, index, reference.raw_text),
                metadata=BibEntryRecord(
                    key=str(reference.number)
                    if reference.number is not None
                    else f"ref-{index + 1}",
                    entry_type="misc",
                    raw_text=reference.raw_text,
                    title=reference.title or "",
                    authors=reference.authors or [],
                    year=reference.year,
                    venue=reference.venue or "",
                    doi=reference.doi or "",
                ),
                metadata_source=reference.metadata_source or "raw_text_heuristic",
                number=reference.number,
                page_start=reference.page_start,
                page_end=reference.page_end,
            )
            for index, reference in enumerate(references.references)
        ]
    if not entries:
        warnings.append(
            "No reference entries were extracted; this is not a successful existence check."
        )
    return paper_id, expected_type, entries, warnings
