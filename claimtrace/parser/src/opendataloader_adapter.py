"""Adapter between OpenDataLoader PDF and ClaimTrace.

OpenDataLoader PDF is responsible for general PDF layout analysis.
This module converts its JSON output into stable ClaimTrace data
structures so the rest of the project does not depend directly on
third-party JSON field names.
"""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class PDFConversionError(RuntimeError):
    """Raised when OpenDataLoader cannot produce usable JSON output."""


@dataclass
class DocumentElement:
    """A normalized document element extracted from a PDF."""

    element_id: str
    element_type: str
    content: str
    page: int
    bbox: tuple[float, float, float, float] | None = None
    font: str | None = None
    font_size: float | None = None
    heading_level: int | None = None


@dataclass
class ConvertedDocument:
    """Normalized representation of an OpenDataLoader document."""

    file_name: str
    title: str | None
    author: str | None
    page_count: int
    elements: list[DocumentElement]


def _normalise_bbox(value: Any) -> tuple[float, float, float, float] | None:
    """Convert an OpenDataLoader bounding box into a tuple."""

    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return None

    try:
        return tuple(float(number) for number in value)
    except (TypeError, ValueError):
        return None


def _normalise_page(value: Any, inherited_page: int | None = None) -> int:
    """Return a valid one-indexed page number."""

    candidate = value if value is not None else inherited_page

    try:
        page = int(candidate)
    except (TypeError, ValueError):
        page = 0

    return max(page, 0)


def _flatten_elements(
    node: Any,
    output: list[DocumentElement],
    inherited_page: int | None = None,
) -> None:
    """Recursively flatten OpenDataLoader's hierarchical JSON tree."""

    if isinstance(node, list):
        for child in node:
            _flatten_elements(child, output, inherited_page)
        return

    if not isinstance(node, dict):
        return

    page = _normalise_page(
        node.get("page number"),
        inherited_page=inherited_page,
    )

    element_type = str(node.get("type", "")).strip().lower()
    content = node.get("content")

    # Some versions or element types may use "text".
    if not isinstance(content, str):
        content = node.get("text")

    if isinstance(content, str):
        # Keep meaningful line boundaries. They are useful for detecting
        # hanging indents and multiple references inside one PDF element.
        normalized_lines = [
            " ".join(line.split()).strip()
            for line in content.splitlines()
            if line.strip()
        ]
        content = "\n".join(normalized_lines)
    else:
        content = ""

    if content:
        raw_id = node.get("id")
        element_id = (
            str(raw_id)
            if raw_id is not None
            else f"element-{len(output) + 1:05d}"
        )

        raw_heading_level = node.get("heading level")
        try:
            heading_level = (
                int(raw_heading_level)
                if raw_heading_level is not None
                else None
            )
        except (TypeError, ValueError):
            heading_level = None

        raw_font_size = node.get("font size")
        try:
            font_size = (
                float(raw_font_size)
                if raw_font_size is not None
                else None
            )
        except (TypeError, ValueError):
            font_size = None

        output.append(
            DocumentElement(
                element_id=element_id,
                element_type=element_type or "unknown",
                content=content,
                page=page,
                bbox=_normalise_bbox(node.get("bounding box")),
                font=str(node["font"]) if node.get("font") else None,
                font_size=font_size,
                heading_level=heading_level,
            )
        )

        # Text elements normally contain their complete text in "content".
        # Returning here prevents duplicate text from nested child nodes.
        if element_type in {
            "paragraph",
            "heading",
            "caption",
            "list item",
            "list-item",
        }:
            return

    for child_key in ("kids", "children", "list items", "rows", "cells"):
        children = node.get(child_key)
        if children:
            _flatten_elements(children, output, inherited_page=page)


def load_opendataloader_json(json_path: Path) -> ConvertedDocument:
    """Load and normalize an existing OpenDataLoader JSON file."""

    json_path = Path(json_path)

    if not json_path.is_file():
        raise PDFConversionError(
            f"OpenDataLoader JSON file does not exist: {json_path}"
        )

    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PDFConversionError(
            f"Could not read OpenDataLoader JSON: {json_path}"
        ) from exc

    if not isinstance(data, dict):
        raise PDFConversionError(
            "OpenDataLoader output must contain a JSON object."
        )

    elements: list[DocumentElement] = []
    _flatten_elements(data.get("kids", []), elements)

    try:
        page_count = int(data.get("number of pages", 0))
    except (TypeError, ValueError):
        page_count = 0

    return ConvertedDocument(
        file_name=str(data.get("file name", json_path.stem)),
        title=str(data["title"]) if data.get("title") else None,
        author=str(data["author"]) if data.get("author") else None,
        page_count=page_count,
        elements=elements,
    )


def _find_generated_json(
    output_dir: Path,
    pdf_path: Path,
) -> Path:
    """Find the JSON generated for a PDF.

    This does not assume one exact output-directory layout because
    OpenDataLoader versions may place generated files differently.
    """

    json_files = list(output_dir.rglob("*.json"))

    if not json_files:
        raise PDFConversionError(
            "OpenDataLoader finished without producing a JSON file."
        )

    matching = [
        path
        for path in json_files
        if path.stem == pdf_path.stem
        or path.name.startswith(f"{pdf_path.stem}.")
        or pdf_path.stem in path.stem
    ]

    if len(matching) == 1:
        return matching[0]

    if len(json_files) == 1:
        return json_files[0]

    if matching:
        return sorted(matching)[0]

    raise PDFConversionError(
        "More than one JSON file was generated and the source PDF "
        f"could not be matched. Candidates: {json_files}"
    )


def convert_pdf(pdf_path: Path) -> ConvertedDocument:
    """Convert one PDF with OpenDataLoader and return normalized elements.

    OpenDataLoader writes its result to an output directory. A temporary
    directory is used here so generated intermediate files do not enter
    the repository.
    """

    pdf_path = Path(pdf_path).resolve()

    if not pdf_path.is_file():
        raise FileNotFoundError(f"PDF file does not exist: {pdf_path}")

    if pdf_path.suffix.lower() != ".pdf":
        raise ValueError(f"Expected a PDF file, received: {pdf_path.name}")

    try:
        import opendataloader_pdf
    except ImportError as exc:
        raise PDFConversionError(
            "opendataloader-pdf is not installed. Install the parser "
            "package and ensure Java 11+ is available."
        ) from exc

    with tempfile.TemporaryDirectory(prefix="claimtrace-pdf-") as temp_dir:
        output_dir = Path(temp_dir)

        try:
            opendataloader_pdf.convert(
                input_path=str(pdf_path),
                output_dir=str(output_dir),
                format="json",
                image_output="off",
                quiet=True,
            )
        except Exception as exc:
            raise PDFConversionError(
                f"OpenDataLoader failed to convert {pdf_path.name}: {exc}"
            ) from exc

        generated_json = _find_generated_json(output_dir, pdf_path)
        return load_opendataloader_json(generated_json)
