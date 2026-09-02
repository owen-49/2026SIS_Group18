"""Adapter between the backend contract and Yi Jiang's PDF Parser.

The Parser converts a PDF to Markdown and extracts images. The backend keeps
the Markdown artifact under its parsed output directory, then exposes a small
paragraph/page contract to the verification pipeline.
"""

from __future__ import annotations

import re
from pathlib import Path

import fitz
from parser.markdown_converter import convert_pdf_to_markdown

from ..config import get_settings
from ..models import ParsedDocument, ParsedParagraph


class ParserAdapterError(RuntimeError):
    """Raised when an uploaded file cannot be prepared for parsing."""


_IMAGE_REF_RE = re.compile(r"!\[[^\]]*\]\((?:<[^>]+>|[^)\s]+)\)")
_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*$")


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
            page_count = max(document.page_count, 1)

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

    paragraphs = _markdown_to_paragraphs(markdown, page_texts)
    display_title = _title_from_markdown(markdown) or title or file_path.stem

    return ParsedDocument(
        paper_id=paper_id,
        title=display_title,
        pages=page_count,
        paragraphs=paragraphs,
    )
