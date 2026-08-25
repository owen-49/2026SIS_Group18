"""Local JSON persistence for serialised Parser output."""

import json
import os
from pathlib import Path

from pydantic import ValidationError

from ..config import get_settings
from ..models import ParsedDocument

PARSED_DIR = get_settings().parsed_dir


class ParsedDocumentStoreError(RuntimeError):
    """Raised when a parsed document cannot be stored or loaded safely."""


def save_parsed_document(
    document: ParsedDocument,
    *,
    parsed_dir: Path | None = None,
) -> Path:
    """Atomically persist Parser output and return its JSON path."""
    target_dir = parsed_dir or PARSED_DIR
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
        raise ParsedDocumentStoreError(
            f"Unable to persist parsed document: {document.paper_id}"
        ) from exc

    return target


def load_parsed_document(path: Path) -> ParsedDocument:
    """Load and validate a previously persisted Parser result."""
    try:
        with path.open("r", encoding="utf-8") as stream:
            data = json.load(stream)
        return ParsedDocument.model_validate(data)
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        raise ParsedDocumentStoreError(f"Unable to read parsed document: {path}") from exc
