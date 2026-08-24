"""Atomic JSON persistence for uploaded paper metadata.

This store is intentionally local and single-process. A process-level lock
protects read-modify-write operations while the application runs with one
Uvicorn worker.
"""

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock
from typing import Any

from pydantic import ValidationError

from ..config import get_settings
from ..models import PaperRecord

PAPERS_FILE = get_settings().papers_file
STORE_VERSION = 1

_STORE_LOCK = RLock()
_UPDATABLE_FIELDS = {
    "status",
    "pages",
    "paragraph_count",
    "entry_count",
    "title",
    "error_message",
}


class PaperStoreError(RuntimeError):
    """Raised when persisted metadata cannot be read or written safely."""


class DuplicatePaperError(PaperStoreError):
    """Raised when a paper ID already exists."""


def _empty_store() -> dict[str, Any]:
    return {"version": STORE_VERSION, "papers": {}}


def _read_store(papers_file: Path) -> dict[str, Any]:
    if not papers_file.exists():
        return _empty_store()

    try:
        with papers_file.open("r", encoding="utf-8") as stream:
            data = json.load(stream)
    except (OSError, json.JSONDecodeError) as exc:
        raise PaperStoreError(f"Unable to read paper metadata: {papers_file}") from exc

    if (
        not isinstance(data, dict)
        or data.get("version") != STORE_VERSION
        or not isinstance(data.get("papers"), dict)
    ):
        raise PaperStoreError(f"Invalid paper metadata format: {papers_file}")

    return data


def _write_store(papers_file: Path, data: dict[str, Any]) -> None:
    papers_file.parent.mkdir(parents=True, exist_ok=True)
    temporary_file = papers_file.with_name(f".{papers_file.name}.tmp")

    try:
        with temporary_file.open("w", encoding="utf-8", newline="\n") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_file, papers_file)
    except OSError as exc:
        temporary_file.unlink(missing_ok=True)
        raise PaperStoreError(f"Unable to write paper metadata: {papers_file}") from exc


def create_paper(
    record: PaperRecord,
    *,
    papers_file: Path | None = None,
) -> PaperRecord:
    """Persist a new paper record without overwriting an existing ID."""
    target = papers_file or PAPERS_FILE

    with _STORE_LOCK:
        data = _read_store(target)
        if record.paper_id in data["papers"]:
            raise DuplicatePaperError(f"Paper already exists: {record.paper_id}")

        data["papers"][record.paper_id] = record.model_dump(mode="json")
        _write_store(target, data)

    return record


def get_paper(
    paper_id: str,
    *,
    papers_file: Path | None = None,
) -> PaperRecord | None:
    """Return a persisted paper record, or None when the ID is unknown."""
    target = papers_file or PAPERS_FILE

    with _STORE_LOCK:
        data = _read_store(target)
        raw_record = data["papers"].get(paper_id)

    if raw_record is None:
        return None

    try:
        return PaperRecord.model_validate(raw_record)
    except ValidationError as exc:
        raise PaperStoreError(f"Invalid metadata for paper: {paper_id}") from exc


def list_papers(*, papers_file: Path | None = None) -> list[PaperRecord]:
    """Return all persisted paper records ordered from newest to oldest."""
    target = papers_file or PAPERS_FILE

    with _STORE_LOCK:
        data = _read_store(target)
        try:
            records = [
                PaperRecord.model_validate(raw_record)
                for raw_record in data["papers"].values()
            ]
        except ValidationError as exc:
            raise PaperStoreError("Invalid paper metadata in store.") from exc

    return sorted(records, key=lambda record: record.created_at, reverse=True)


def update_paper(
    paper_id: str,
    updates: dict[str, Any],
    *,
    papers_file: Path | None = None,
) -> PaperRecord | None:
    """Update mutable fields on a paper record and return the new value."""
    unsupported_fields = set(updates) - _UPDATABLE_FIELDS
    if unsupported_fields:
        fields = ", ".join(sorted(unsupported_fields))
        raise ValueError(f"Fields cannot be updated: {fields}")

    target = papers_file or PAPERS_FILE

    with _STORE_LOCK:
        data = _read_store(target)
        raw_record = data["papers"].get(paper_id)
        if raw_record is None:
            return None

        try:
            record = PaperRecord.model_validate(raw_record)
            updated_data = record.model_dump()
            updated_data.update(updates)
            updated_data["updated_at"] = datetime.now(UTC)
            updated_record = PaperRecord.model_validate(updated_data)
        except ValidationError as exc:
            raise PaperStoreError(f"Invalid metadata for paper: {paper_id}") from exc

        data["papers"][paper_id] = updated_record.model_dump(mode="json")
        _write_store(target, data)

    return updated_record
