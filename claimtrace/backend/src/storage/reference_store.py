"""Read the Parser's public Reference JSON and persist backend extraction results."""

import hashlib
import os
import tempfile
from pathlib import Path
from uuid import UUID

from pydantic import BaseModel, Field, ValidationError

from . import parsed_document_store


class ReferenceStoreError(RuntimeError):
    """An existing artifact is invalid or cannot be persisted."""


class StoredReference(BaseModel):
    raw_text: str = Field(min_length=1)
    number: int | None = None
    page_start: int | None = Field(default=None, ge=1)
    page_end: int | None = Field(default=None, ge=1)


class StoredReferenceList(BaseModel):
    # source_file + references[].raw_text is the current Parser public schema.
    source_file: str = Field(min_length=1)
    references: list[StoredReference]
    warnings: list[str] = Field(default_factory=list)
    paper_id: str | None = None
    source_sha256: str | None = None


def reference_path(paper_id: str) -> Path:
    return parsed_document_store.PARSED_DIR / f"{UUID(paper_id)}.references.json"


def source_digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def load_references(paper_id: str) -> StoredReferenceList | None:
    path = reference_path(paper_id)
    try:
        payload = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise ReferenceStoreError("Unable to read persisted reference JSON.") from exc
    try:
        result = StoredReferenceList.model_validate_json(payload)
        if result.paper_id is not None and result.paper_id != paper_id:
            raise ValueError("Reference artifact belongs to another paper.")
        return result
    except (ValueError, ValidationError) as exc:
        raise ReferenceStoreError("Persisted reference JSON is invalid.") from exc


def save_references(paper_id: str, result: StoredReferenceList) -> None:
    target = reference_path(paper_id)
    temporary = None
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=target.parent,
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            stream.write(result.model_dump_json(indent=2) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    except OSError as exc:
        raise ReferenceStoreError("Unable to persist reference JSON.") from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def invalidate_references(paper_id: str) -> None:
    """Explicit PDF reprocessing invalidates the previous reference artifact."""
    reference_path(paper_id).unlink(missing_ok=True)
