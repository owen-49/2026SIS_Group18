"""Persist bibliography reports using the existing local JSON storage layout."""

import os
import tempfile
from pathlib import Path
from uuid import UUID

from ..audit_models import BibliographyAuditResponse
from . import parsed_document_store


def save_audit(report: BibliographyAuditResponse) -> None:
    directory = parsed_document_store.PARSED_DIR / "audits"
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{UUID(report.audit_id)}.json"
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=directory,
            delete=False,
            suffix=".tmp",
        ) as stream:
            temporary = Path(stream.name)
            stream.write(report.model_dump_json(indent=2) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def load_audit(audit_id: UUID) -> BibliographyAuditResponse:
    path = parsed_document_store.PARSED_DIR / "audits" / f"{audit_id}.json"
    report = BibliographyAuditResponse.model_validate_json(path.read_text(encoding="utf-8"))
    if report.audit_id != str(audit_id):
        raise ValueError("Stored audit ID does not match the request.")
    return report
