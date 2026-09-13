"""Delete uploaded papers and recover interrupted local artifact cleanup."""

import hashlib
import json
import os
import shutil
from enum import Enum
from pathlib import Path
from threading import RLock
from typing import Any
from uuid import uuid4

from ..config import get_settings
from ..models import PaperRecord
from ..storage import bib_document_store, parsed_document_store
from ..storage.paper_store import PaperStoreError, delete_paper, get_paper
from .paper_lifecycle import paper_lifecycle_lock

UPLOAD_DIR = get_settings().upload_dir
_DELETION_LOCK = RLock()
_JOURNAL_VERSION = 1


class PaperDeletionNotFoundError(RuntimeError):
    """Raised when the requested paper is not in the local library."""


class PaperDeletionError(RuntimeError):
    """Raised when a paper and its artifacts cannot be deleted safely."""


class PaperDeletionOutcome(str, Enum):
    """Externally visible state after a delete request."""

    DELETED = "deleted"
    CLEANUP_PENDING = "cleanup_pending"


def _approved_roots() -> tuple[Path, ...]:
    return (
        UPLOAD_DIR.resolve(),
        parsed_document_store.PARSED_DIR.resolve(),
        bib_document_store.BIB_PARSED_DIR.resolve(),
    )


def _safe_artifact(path: Path, roots: tuple[Path, ...]) -> Path:
    """Resolve an artifact path and ensure it stays inside an approved root."""
    resolved = path.resolve()
    resolved_roots = tuple(root.resolve() for root in roots)
    if not any(resolved != root and resolved.is_relative_to(root) for root in resolved_roots):
        raise PaperDeletionError("Paper metadata contains an unsafe artifact path.")
    return resolved


def _journal_directory() -> Path:
    return UPLOAD_DIR / ".pending-deletions"


def _journal_path(paper_id: str) -> Path:
    digest = hashlib.sha256(paper_id.encode("utf-8")).hexdigest()
    return _journal_directory() / f"{digest}.json"


def _write_journal(
    paper_id: str,
    token: str,
    staged: list[tuple[Path, Path]],
) -> Path:
    directory = _journal_directory()
    directory.mkdir(parents=True, exist_ok=True)
    target = _journal_path(paper_id)
    temporary = target.with_name(f".{target.name}.{uuid4().hex}.tmp")
    payload = {
        "version": _JOURNAL_VERSION,
        "paper_id": paper_id,
        "token": token,
        "artifacts": [
            {"original": str(original), "temporary": str(staged_path)}
            for original, staged_path in staged
        ],
    }
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    except OSError as exc:
        temporary.unlink(missing_ok=True)
        raise PaperDeletionError("Unable to record pending paper cleanup.") from exc
    return target


def _read_journal(path: Path) -> tuple[str, list[tuple[Path, Path]]]:
    try:
        payload: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PaperDeletionError("Unable to read pending paper cleanup.") from exc
    if (
        not isinstance(payload, dict)
        or payload.get("version") != _JOURNAL_VERSION
        or not isinstance(payload.get("paper_id"), str)
        or not isinstance(payload.get("token"), str)
        or not isinstance(payload.get("artifacts"), list)
    ):
        raise PaperDeletionError("Pending paper cleanup has an invalid format.")

    token = payload["token"]
    roots = _approved_roots()
    staged: list[tuple[Path, Path]] = []
    for item in payload["artifacts"]:
        if not isinstance(item, dict):
            raise PaperDeletionError("Pending paper cleanup has an invalid artifact.")
        original_raw = item.get("original")
        temporary_raw = item.get("temporary")
        if not isinstance(original_raw, str) or not isinstance(temporary_raw, str):
            raise PaperDeletionError("Pending paper cleanup has an invalid artifact.")
        original = _safe_artifact(Path(original_raw), roots)
        temporary = _safe_artifact(Path(temporary_raw), roots)
        expected_name = f".{original.name}.deleting-{token}"
        if temporary.parent != original.parent or temporary.name != expected_name:
            raise PaperDeletionError("Pending paper cleanup contains unsafe staging metadata.")
        staged.append((original, temporary))
    return payload["paper_id"], staged


def _remove_staged_artifact(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink(missing_ok=True)


def _remove_journal(path: Path) -> None:
    path.unlink(missing_ok=True)
    try:
        path.parent.rmdir()
    except OSError:
        pass


def _restore_staged(staged: list[tuple[Path, Path]]) -> None:
    """Best-effort restoration when metadata still owns the paper."""
    failures: list[OSError] = []
    for original, temporary in reversed(staged):
        if not temporary.exists():
            continue
        try:
            if original.exists():
                raise OSError("The original artifact already exists.")
            os.replace(temporary, original)
        except OSError as exc:
            failures.append(exc)
    if failures:
        raise PaperDeletionError("Unable to restore staged paper artifacts.") from failures[0]


def _finish_committed_cleanup(staged: list[tuple[Path, Path]], journal: Path) -> bool:
    """Purge staged artifacts, retaining the journal when a retry is needed."""
    cleanup_failed = False
    for _original, temporary in staged:
        if not temporary.exists():
            continue
        try:
            _remove_staged_artifact(temporary)
        except OSError:
            cleanup_failed = True
    if cleanup_failed:
        return False
    try:
        _remove_journal(journal)
    except OSError:
        return False
    return True


def _recover_journal(journal: Path) -> bool:
    """Finish a committed deletion or roll back one interrupted before commit."""
    paper_id, staged = _read_journal(journal)
    try:
        record = get_paper(paper_id)
    except PaperStoreError as exc:
        raise PaperDeletionError("Unable to read paper metadata during recovery.") from exc

    if record is not None:
        _restore_staged(staged)
        try:
            _remove_journal(journal)
        except OSError as exc:
            raise PaperDeletionError("Unable to complete paper deletion rollback.") from exc
        return True
    return _finish_committed_cleanup(staged, journal)


def recover_pending_deletions() -> int:
    """Recover all durable deletion journals; return the number still pending."""
    directory = _journal_directory()
    if not directory.is_dir():
        return 0

    pending = 0
    for journal in directory.glob("*.json"):
        try:
            paper_id, _staged = _read_journal(journal)
            with paper_lifecycle_lock(paper_id), _DELETION_LOCK:
                if not _recover_journal(journal):
                    pending += 1
        except (OSError, PaperDeletionError):
            pending += 1
    return pending


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
                raise PaperDeletionError("Unsupported paper artifact.")
            seen.add(resolved)
            artifacts.append(resolved)

    for audit_path in _audit_artifacts(record.paper_id, parsed_root):
        if audit_path not in seen:
            seen.add(audit_path)
            artifacts.append(audit_path)
    return artifacts


def delete_uploaded_paper(paper_id: str) -> PaperDeletionOutcome:
    """Remove a paper record and its local artifacts, with durable cleanup recovery."""
    with paper_lifecycle_lock(paper_id), _DELETION_LOCK:
        journal = _journal_path(paper_id)
        if journal.exists():
            if _recover_journal(journal):
                try:
                    if get_paper(paper_id) is None:
                        return PaperDeletionOutcome.DELETED
                except PaperStoreError as exc:
                    raise PaperDeletionError("Unable to read paper metadata.") from exc
            else:
                return PaperDeletionOutcome.CLEANUP_PENDING
        return _delete_uploaded_paper(paper_id)


def _delete_uploaded_paper(paper_id: str) -> PaperDeletionOutcome:
    """Perform a new deletion while lifecycle and deletion locks are held."""
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
    planned = [
        (original, original.with_name(f".{original.name}.deleting-{token}"))
        for original in artifacts
    ]
    journal = _write_journal(paper_id, token, planned)
    staged: list[tuple[Path, Path]] = []
    try:
        for original, temporary in planned:
            os.replace(original, temporary)
            staged.append((original, temporary))
    except OSError as exc:
        try:
            _restore_staged(staged)
            _remove_journal(journal)
        except (OSError, PaperDeletionError) as restore_exc:
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
            _remove_journal(journal)
        except (OSError, PaperDeletionError) as restore_exc:
            raise PaperDeletionError(
                "Unable to update metadata or restore paper artifacts."
            ) from restore_exc
        if isinstance(exc, PaperDeletionNotFoundError):
            raise
        raise PaperDeletionError("Unable to update paper metadata.") from exc

    if _finish_committed_cleanup(staged, journal):
        return PaperDeletionOutcome.DELETED
    return PaperDeletionOutcome.CLEANUP_PENDING
