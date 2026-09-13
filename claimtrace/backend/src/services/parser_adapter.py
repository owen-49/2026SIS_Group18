"""Adapter between the backend contract and the repository PDF parsers.

Yi Jiang's Parser converts a PDF to Markdown and extracts images.  The
backend keeps the Markdown artifact under its parsed output directory, then
exposes a small paragraph/page contract to the verification pipeline.  The
repository Parser is also used for conservative first-page metadata
extraction needed by BibTeX verification.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import fitz
from parser.markdown_converter import convert_pdf_to_markdown

from ..config import get_settings
from ..models import ParsedDocument, ParsedParagraph


class ParserAdapterError(RuntimeError):
    """Raised when an uploaded file cannot be prepared for parsing."""


_IMAGE_REF_RE = re.compile(r"!\[[^\]]*\]\((?:<[^>]+>|[^)\s]+)\)")
_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*$")
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


def _normalise_for_matching(text: str) -> str:
    """Return a whitespace-normalised representation for page matching."""
    return " ".join(re.findall(r"\w+", text.casefold(), flags=re.UNICODE))


def _clean_markdown_block(block: str) -> str:
    """Turn one Markdown block into searchable plain text."""
    cleaned_lines: list[str] = []
    for raw_line in block.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("```") or line in {"---", "***", "___"}:
            continue

        line = _IMAGE_REF_RE.sub("", line).strip()
        line = re.sub(r"^\s{0,3}#{1,6}\s+", "", line)
        line = re.sub(r"^\s*(?:[-*+] |\d+[.)] )", "", line)
        line = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", line)
        line = re.sub(r"`([^`]+)`", r"\1", line)
        line = re.sub(r"\s+", " ", line).strip()
        if line:
            cleaned_lines.append(line)

    return "\n".join(cleaned_lines).strip()


def _page_for_block(
    text: str,
    page_texts: list[str],
    fallback_page: int,
) -> int:
    """Estimate the PDF page containing a converted Markdown block."""
    target = _normalise_for_matching(text)
    if not target:
        return fallback_page

    target_tokens = set(target.split())
    best_page = fallback_page
    best_score = 0.0

    for index, page_text in enumerate(page_texts, start=1):
        page = _normalise_for_matching(page_text)
        if not page:
            continue
        if target in page:
            return index

        page_tokens = set(page.split())
        overlap = len(target_tokens & page_tokens) / max(len(target_tokens), 1)
        if overlap > best_score:
            best_score = overlap
            best_page = index

    return best_page if best_score > 0 else fallback_page


def _markdown_to_paragraphs(markdown: str, page_texts: list[str]) -> list[ParsedParagraph]:
    """Convert Markdown blocks into the backend's stable paragraph contract."""
    paragraphs: list[ParsedParagraph] = []
    fallback_page = 1

    for block in re.split(r"\n\s*\n+", markdown.strip()):
        text = _clean_markdown_block(block)
        if not text:
            continue

        page = _page_for_block(text, page_texts, fallback_page)
        fallback_page = page
        paragraphs.append(ParsedParagraph(text=text, page_start=page, page_end=page))

    return paragraphs


def _title_from_markdown(markdown: str) -> str | None:
    """Return the first Markdown heading as a document title, if present."""
    for line in markdown.splitlines():
        match = _HEADING_RE.match(line)
        if match:
            title = _clean_markdown_block(match.group(1))
            if title:
                return title
    return None


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
        # A single comma is normally the surname/given-name separator in
        # "Last, First". Only split comma-delimited author lists when there
        # is more than one comma (or an explicit and/semicolon separator).
        parts = [cleaned] if cleaned.count(",") == 1 else re.split(
            r"\s*,\s*(?=[A-Z][A-Za-z'’.-]+(?:\s|$))", cleaned
        )
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
    output_dir: Path | None = None,
) -> ParsedDocument:
    """Convert an uploaded PDF with Yi's Parser and return backend output."""
    if not file_path.is_file():
        raise ParserAdapterError(f"Uploaded file not found: {file_path}")
    if file_path.suffix.lower() != ".pdf":
        raise ParserAdapterError("The PDF Parser only accepts PDF files.")

    settings = get_settings()
    markdown_dir = output_dir or settings.parsed_dir / "markdown"

    try:
        with fitz.open(file_path) as document:
            page_texts = [page.get_text("text") for page in document]
            page_count = document.page_count
    except Exception as exc:
        raise ParserAdapterError(f"Unable to inspect PDF: {file_path.name}") from exc

    if page_count < 1:
        raise ParserAdapterError("The PDF contains no pages.")

    try:
        from parser.pdf_parser import parse_pdf
    except ImportError as exc:
        raise ParserAdapterError("The claimtrace-parser package is unavailable.") from exc

    try:
        parsed_paper = parse_pdf(file_path)
    except Exception as exc:  # Parser exceptions vary by implementation and PDF library.
        raise ParserAdapterError(f"Unable to parse PDF metadata: {file_path.name}") from exc

    try:
        markdown = convert_pdf_to_markdown(
            file_path,
            output_dir=markdown_dir,
            hybrid=settings.parser_hybrid,
            hybrid_mode=settings.parser_hybrid_mode,
            hybrid_url=(settings.parser_hybrid_url if settings.parser_hybrid != "off" else None),
            use_struct_tree=settings.parser_use_struct_tree,
        )
    except Exception as exc:
        raise ParserAdapterError(f"Unable to convert PDF with Yi's Parser: {exc}") from exc

    metadata = _extract_metadata(parsed_paper, title or file_path.stem)
    paragraphs = _markdown_to_paragraphs(markdown, page_texts)
    display_title = _title_from_markdown(markdown) or metadata.title

    return ParsedDocument(
        paper_id=paper_id,
        title=display_title,
        authors=metadata.authors,
        year=metadata.year,
        venue=metadata.venue,
        doi=metadata.doi,
        pages=page_count,
        paragraphs=paragraphs,
    )
