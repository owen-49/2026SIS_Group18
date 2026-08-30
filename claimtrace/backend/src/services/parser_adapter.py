"""Stable adapter between the backend and the real Parser package."""

import re
from dataclasses import dataclass
from pathlib import Path

from ..models import ParsedDocument, ParsedParagraph


class ParserAdapterError(RuntimeError):
    """Raised when an uploaded file cannot be prepared for parsing."""


_DOI_PATTERN = re.compile(
    r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+",
    re.IGNORECASE,
)
_YEAR_PATTERN = re.compile(r"\b(?:19|20)\d{2}\b")
_VENUE_MARKERS = (
    "journal",
    "transactions",
    "proceedings",
    "conference",
    "workshop",
    "symposium",
    "neurips",
    "nips",
    "icml",
    "iclr",
    "acl",
    "naacl",
    "emnlp",
    "cvpr",
    "iccv",
    "eccv",
    "aaai",
    "ijcai",
    "nature",
    "science",
    "arxiv",
)


@dataclass(frozen=True)
class _ExtractedMetadata:
    """Metadata values normalized at the backend/Parser boundary."""

    title: str | None
    authors: list[str]
    year: int | None
    venue: str | None
    doi: str | None


def _clean_metadata_line(value: str) -> str:
    """Collapse layout whitespace and remove common author footnote marks."""
    value = re.sub(r"\s+", " ", value).strip()
    return re.sub(r"[†‡*]+$", "", value).strip()


def _first_page_lines(parsed_paper: object) -> list[str]:
    """Return readable first-page lines from the Parser's raw blocks."""
    raw_blocks = getattr(parsed_paper, "raw_blocks", None) or []
    ordered_blocks = sorted(
        (block for block in raw_blocks if getattr(block, "page", 0) == 1),
        key=lambda block: (
            getattr(block, "bbox", (0, 0, 0, 0))[1],
            getattr(block, "bbox", (0, 0, 0, 0))[0],
        ),
    )
    lines: list[str] = []
    for block in ordered_blocks:
        text = getattr(block, "text", "")
        for raw_line in text.splitlines():
            line = _clean_metadata_line(raw_line)
            if line:
                lines.append(line)
    return lines


def _looks_like_author_line(value: str) -> bool:
    """Identify a likely author line without treating title punctuation as names."""
    lowered = value.lower()
    if any(marker in lowered for marker in ("abstract", "keywords", "doi.org", "@")):
        return False
    if _YEAR_PATTERN.search(value) or len(value.split()) < 2:
        return False
    if len(value) > 240 or value.endswith((".", ":")):
        return False
    return "," in value or bool(re.search(r"\b(?:and|&|et al\.)\b", value, re.IGNORECASE))


def _split_author_line(value: str) -> list[str]:
    """Split common comma/and-separated author presentations."""
    cleaned = re.sub(r"\s*\([^)]*\)", "", value)
    parts = re.split(r"\s+(?:and|&)\s+|\s*;\s*", cleaned, flags=re.IGNORECASE)
    if len(parts) == 1 and "," in cleaned:
        parts = re.split(r"\s*,\s*(?=[A-Z][A-Za-z'’.-]+(?:\s|$))", cleaned)
    return [part.strip(" ,") for part in parts if part.strip(" ,")]


def _extract_doi(lines: list[str]) -> str:
    """Extract and normalize the first DOI printed on the first page."""
    for line in lines:
        match = _DOI_PATTERN.search(line)
        if match:
            return match.group(0).rstrip(".,;:)]}")
    return ""


def _extract_metadata(parsed_paper: object, fallback_title: str | None) -> _ExtractedMetadata:
    """Read Parser fields and use conservative first-page fallbacks."""
    lines = _first_page_lines(parsed_paper)
    parser_title = getattr(parsed_paper, "title", None) or None
    parser_authors = list(getattr(parsed_paper, "authors", None) or [])
    parser_year = getattr(parsed_paper, "year", None)
    parser_venue = getattr(parsed_paper, "venue", None) or None
    parser_doi = getattr(parsed_paper, "doi", None) or None

    author_index = next(
        (index for index, line in enumerate(lines[:12]) if _looks_like_author_line(line)),
        None,
    )
    metadata_signal = (
        author_index is not None
        or any(_YEAR_PATTERN.search(line) for line in lines[:12])
        or bool(_extract_doi(lines[:12]))
    )

    inferred_title = parser_title
    if not inferred_title and metadata_signal:
        for line in lines[:12]:
            lowered = line.lower()
            if (
                len(line) >= 5
                and len(line) <= 240
                and not _looks_like_author_line(line)
                and not lowered.startswith(("abstract", "keywords", "doi", "http", "arxiv"))
                and not _YEAR_PATTERN.fullmatch(line)
            ):
                inferred_title = line
                break

    inferred_authors = parser_authors
    if not inferred_authors and author_index is not None:
        inferred_authors = _split_author_line(lines[author_index])

    inferred_year = parser_year
    if inferred_year is None:
        year_match = next(
            (match for line in lines[:12] if (match := _YEAR_PATTERN.search(line))),
            None,
        )
        inferred_year = int(year_match.group(0)) if year_match else None

    inferred_venue = parser_venue
    if not inferred_venue:
        for line in lines[:16]:
            lowered = line.lower()
            if any(marker in lowered for marker in _VENUE_MARKERS):
                inferred_venue = _YEAR_PATTERN.sub("", line).strip(" ,.-")
                break

    return _ExtractedMetadata(
        title=inferred_title or fallback_title,
        authors=inferred_authors,
        year=inferred_year,
        venue=inferred_venue,
        doi=parser_doi or _extract_doi(lines[:16]) or None,
    )


def parse_document(
    paper_id: str,
    file_path: Path,
    *,
    title: str | None = None,
) -> ParsedDocument:
    """Parse a PDF with the repository Parser and return the backend contract."""
    if not file_path.is_file():
        raise ParserAdapterError(f"Uploaded file not found: {file_path}")
    if file_path.suffix.lower() != ".pdf":
        raise ParserAdapterError("The Parser adapter only accepts PDF files.")

    try:
        from parser.pdf_parser import parse_pdf
    except ImportError as exc:
        raise ParserAdapterError("The claimtrace-parser package is unavailable.") from exc

    try:
        parsed_paper = parse_pdf(file_path)
    except Exception as exc:  # Parser exceptions vary by implementation and PDF library.
        raise ParserAdapterError(f"Unable to parse PDF: {file_path.name}") from exc

    pages = int(getattr(parsed_paper, "pages", 0) or 0)
    if pages < 1:
        raise ParserAdapterError("The Parser returned no PDF pages.")

    try:
        paragraphs = [
            ParsedParagraph(
                text=paragraph.text,
                page_start=paragraph.page_start,
                page_end=paragraph.page_end,
            )
            for paragraph in getattr(parsed_paper, "paragraphs", [])
        ]
        metadata = _extract_metadata(parsed_paper, title or file_path.stem)
        return ParsedDocument(
            paper_id=paper_id,
            title=metadata.title,
            authors=metadata.authors,
            year=metadata.year,
            venue=metadata.venue,
            doi=metadata.doi,
            pages=pages,
            paragraphs=paragraphs,
        )
    except Exception as exc:
        raise ParserAdapterError("The Parser output did not match the backend contract.") from exc
