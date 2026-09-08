"""Delete one uploaded paper and its local derived artifacts."""

import json
import os
import shutil
from pathlib import Path
from threading import RLock
from uuid import uuid4

from ..config import get_settings
from ..models import PaperRecord
from ..storage import bib_document_store, parsed_document_store
from ..storage.paper_store import PaperStoreError, delete_paper, get_paper

UPLOAD_DIR = get_settings().upload_dir
_DELETION_LOCK = RLock()


class PaperDeletionNotFoundError(RuntimeError):
    """Raised when the requested paper is not in the local library."""


class PaperDeletionError(RuntimeError):
    """Raised when a paper and its artifacts cannot be deleted safely."""


def _safe_artifact(path: Path, roots: tuple[Path, ...]) -> Path:
    """Resolve an artifact path and ensure it stays inside an approved root."""
    resolved = path.resolve()
    resolved_roots = tuple(root.resolve() for root in roots)
    if not any(resolved != root and resolved.is_relative_to(root) for root in resolved_roots):
        raise PaperDeletionError("Paper metadata contains an unsafe artifact path.")
    return resolved


def _audit_artifacts(paper_id: str, parsed_root: Path) -> list[Path]:
    """Return stored audit reports whose input is the paper being deleted."""
    audit_dir = parsed_root / "audits"
    if not audit_dir.is_dir():
        return []

    artifacts: list[Path] = []
    for candidate in audit_dir.glob("*.json"):
        safe_candidate = _safe_artifact(candidate, (parsed_root,))
        try:
            payload = json.loads(safe_candidate.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict) and payload.get("input_paper_id") == paper_id:
            artifacts.append(safe_candidate)
    return artifacts


def _artifact_paths(record: PaperRecord) -> list[Path]:
    """Collect existing local files and directories owned by one paper."""
    upload_root = UPLOAD_DIR.resolve()
    parsed_root = parsed_document_store.PARSED_DIR.resolve()
    bib_root = bib_document_store.BIB_PARSED_DIR.resolve()
    storage_stem = Path(record.stored_filename).stem

    candidates: list[tuple[Path, tuple[Path, ...]]] = [
        (Path(record.file_path), (upload_root,)),
        (parsed_root / f"{record.paper_id}.json", (parsed_root,)),
        (bib_root / f"{record.paper_id}.json", (bib_root, parsed_root)),
        (parsed_root / f"{record.paper_id}.references.json", (parsed_root,)),
        (parsed_root / "markdown" / f"{storage_stem}.md", (parsed_root,)),
        (parsed_root / "markdown" / f"{storage_stem}_images", (parsed_root,)),
    ]
    if record.parsed_result_path:
        candidates.append((Path(record.parsed_result_path), (parsed_root, bib_root)))

    artifacts: list[Path] = []
    seen: set[Path] = set()
    for candidate, roots in candidates:
        resolved = _safe_artifact(candidate, roots)
        if resolved.exists() and resolved not in seen:
            if not (resolved.is_file() or resolved.is_dir()):
                raise PaperDeletionError(f"Unsupported paper artifact: {resolved}")
            seen.add(resolved)
            artifacts.append(resolved)

    for audit_path in _audit_artifacts(record.paper_id, parsed_root):
        if audit_path not in seen:
            seen.add(audit_path)
            artifacts.append(audit_path)
    return artifacts


def _restore_staged(staged: list[tuple[Path, Path]]) -> None:
    """Best-effort restoration when deletion cannot update the paper store."""
    failures: list[OSError] = []
    for original, temporary in reversed(staged):
        if not temporary.exists():
            continue
        try:
            os.replace(temporary, original)
        except OSError as exc:
            failures.append(exc)
    if failures:
        raise PaperDeletionError("Unable to restore staged paper artifacts.") from failures[0]


def delete_uploaded_paper(paper_id: str) -> None:
    """Remove a paper record and all known local artifacts as one operation."""
    with _DELETION_LOCK:
        _delete_uploaded_paper(paper_id)


def _delete_uploaded_paper(paper_id: str) -> None:
    """Perform deletion while the process-level deletion lock is held."""
    try:
        record = get_paper(paper_id)
    except PaperStoreError as exc:
        raise PaperDeletionError("Unable to read paper metadata.") from exc
    if record is None:
        raise PaperDeletionNotFoundError("Paper not found.")

    try:
        artifacts = _artifact_paths(record)
    except OSError as exc:
        raise PaperDeletionError("Unable to inspect paper artifacts.") from exc

    token = uuid4().hex
    staged: list[tuple[Path, Path]] = []
    try:
        for original in artifacts:
            temporary = original.with_name(f".{original.name}.deleting-{token}")
            os.replace(original, temporary)
            staged.append((original, temporary))
    except OSError as exc:
        try:
            _restore_staged(staged)
        except PaperDeletionError as restore_exc:
            raise PaperDeletionError(
                "Unable to stage or restore paper artifacts for deletion."
            ) from restore_exc
        raise PaperDeletionError("Unable to stage paper artifacts for deletion.") from exc

    try:
        deleted = delete_paper(paper_id)
        if deleted is None:
            raise PaperDeletionNotFoundError("Paper not found.")
    except (PaperStoreError, PaperDeletionNotFoundError) as exc:
        try:
            _restore_staged(staged)
        except PaperDeletionError as restore_exc:
            raise PaperDeletionError(
                "Unable to update metadata or restore paper artifacts."
            ) from restore_exc
        if isinstance(exc, PaperDeletionNotFoundError):
            raise
        raise PaperDeletionError("Unable to update paper metadata.") from exc

    cleanup_error: OSError | None = None
    for _original, temporary in staged:
        try:
            if temporary.is_dir():
                shutil.rmtree(temporary)
            else:
                temporary.unlink(missing_ok=True)
        except OSError as exc:
            cleanup_error = cleanup_error or exc
    if cleanup_error is not None:
        raise PaperDeletionError(
            "The paper record was deleted, but local artifact cleanup was incomplete."
        ) from cleanup_error
