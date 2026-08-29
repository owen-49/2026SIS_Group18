"""Local JSON persistence for parsed BibTeX entries."""

import json
import os
from pathlib import Path

from pydantic import ValidationError

from ..config import get_settings
from ..models import ParsedBibDocument

BIB_PARSED_DIR = get_settings().parsed_dir / "bib"


class BibDocumentStoreError(RuntimeError):
    """Raised when parsed BibTeX data cannot be stored or loaded safely."""


def save_bib_document(
    document: ParsedBibDocument,
    *,
    parsed_dir: Path | None = None,
) -> Path:
    """Atomically persist parsed BibTeX entries and return their JSON path."""
    target_dir = parsed_dir or BIB_PARSED_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{document.paper_id}.json"
    temporary = target_dir / f".{document.paper_id}.json.tmp"

    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            json.dump(document.model_dump(mode="json"), stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    except OSError as exc:
        temporary.unlink(missing_ok=True)
        raise BibDocumentStoreError(
            f"Unable to persist parsed BibTeX document: {document.paper_id}"
        ) from exc

    return target


def load_bib_document(path: Path) -> ParsedBibDocument:
    """Load and validate previously persisted BibTeX Parser output."""
    try:
        with path.open("r", encoding="utf-8") as stream:
            data = json.load(stream)
        return ParsedBibDocument.model_validate(data)
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        raise BibDocumentStoreError(f"Unable to read parsed BibTeX document: {path}") from exc
