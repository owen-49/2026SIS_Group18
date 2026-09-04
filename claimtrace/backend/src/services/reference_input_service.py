"""Consume existing Bib storage and the Parser team's reference-list extractor."""

from pathlib import Path
from threading import Lock
from uuid import NAMESPACE_URL, uuid5

from ..audit_models import ReferenceEntry
from ..models import AuditRequest, BibEntryRecord, PaperRecord, ParseStatus
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

_REFERENCE_LOCKS = [Lock() for _ in range(32)]


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


def persisted_pdf_references(record: PaperRecord) -> StoredReferenceList:
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
                return saved
            if not path.is_file():
                raise AuditInputError(
                    500, "INPUT_FILE_MISSING", "Uploaded manuscript PDF is missing."
                )
            digest = source_digest(path)
            extracted = extract_pdf_references(path)
            saved = StoredReferenceList(
                source_file=path.name,
                paper_id=record.paper_id,
                source_sha256=digest,
                references=[
                    StoredReference(
                        raw_text=reference.raw_text,
                        number=reference.number,
                        page_start=reference.page_start,
                        page_end=reference.page_end,
                    )
                    for reference in extracted.references
                ],
                warnings=list(extracted.warnings),
            )
            save_references(record.paper_id, saved)
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
            )
            for index, entry in enumerate(document.entries)
        ]
    else:
        references = persisted_pdf_references(record)
        warnings.extend(references.warnings)
        warnings.append(
            "The existing PDF reference extractor returns raw text and locations, not structured "
            "title/authors/year/venue/DOI. External raw-reference lookup and field extraction "
            "must be supplied by the responsible modules before full metadata verification."
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
                ),
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
