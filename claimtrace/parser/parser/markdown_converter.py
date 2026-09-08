"""PDF to Markdown conversion built on opendataloader-pdf.

The engine consumes clean Markdown text for embedding and retrieval.
This module delegates conversion to opendataloader-pdf (benchmark #1
PDF parser) instead of the hand-rolled PyMuPDF pipeline in
pdf_parser.py, which has weaker table and reading-order recovery.

Two modes:

- Hybrid (default): simple pages stay on the Java side, complex pages
  (tables, scanned content) are routed to a locally running AI backend.
  Start it once with::

      opendataloader-pdf-hybrid --port 5002

  Health endpoint: GET http://localhost:5002/health
- Local: pure Java processing, no backend service. Pass ``hybrid="off"``.

Both modes require Java 11+ on the machine (the CLI is a JVM app).

.. note::
    On Chinese-locale Windows, start the backend with ``PYTHONUTF8=1``
    set, otherwise docling model loading fails with a GBK decoding error.
"""

import re
import shutil
import subprocess
import urllib.error
import urllib.request
import warnings
from contextlib import nullcontext
from pathlib import Path

import opendataloader_pdf

DEFAULT_HYBRID_BACKEND = "docling-fast"
DEFAULT_HYBRID_URL = "http://localhost:5002"
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parents[2] / "generated_markdown"
_HEALTH_CHECK_TIMEOUT_SECONDS = 2.0

# Matches `![](path)` and `![](<path>)` image references.
_IMAGE_REF_RE = re.compile(r"!\[[^\]]*\]\((?:<([^>]+)>|([^)\s]+))\)")


class HybridBackendError(RuntimeError):
    """The hybrid backend is unreachable or the conversion failed."""


def convert_pdf(pdf_path: Path | str) -> Path:
    """Convert a PDF to Markdown using the repository defaults.

    The generated Markdown and extracted images are saved in
    ``generated_markdown``. Uses the Docling hybrid backend when available
    for better formula and scanned-page handling, then falls back to local
    Java processing. Returns the generated Markdown file path.
    """
    pdf_path = Path(pdf_path)
    if is_backend_reachable():
        convert_pdf_to_markdown(
            pdf_path,
            hybrid=DEFAULT_HYBRID_BACKEND,
            hybrid_mode="full",
        )
    else:
        warnings.warn(
            "Docling hybrid backend is unavailable; using local mode. "
            "Formula extraction may be less complete.",
            RuntimeWarning,
            stacklevel=2,
        )
        convert_pdf_to_markdown(pdf_path, hybrid="off")
    return DEFAULT_OUTPUT_DIR / f"{pdf_path.stem}.md"


def is_backend_reachable(
    url: str = DEFAULT_HYBRID_URL,
    timeout: float = _HEALTH_CHECK_TIMEOUT_SECONDS,
) -> bool:
    """Return True if the hybrid backend answers its /health endpoint.

    Args:
        url: Backend base URL (without trailing slash).
        timeout: Health check timeout in seconds.

    Returns:
        True if the backend responds with HTTP 200 on /health.
    """
    try:
        with urllib.request.urlopen(f"{url}/health", timeout=timeout) as response:
            return response.status == 200
    except (urllib.error.URLError, OSError):
        return False


def _deduplicate_image_references(markdown: str) -> str:
    """Keep only the last occurrence of each duplicated image reference.

    The hybrid converter can emit the same figure twice: once in extraction
    order at the document head (without caption context) and once at its
    inline position in the body. Keeping the last occurrence preserves the
    caption context and drops the leading cluster. Only standalone image
    lines are removed; lines mixing text and an image are left untouched.
    """
    lines = markdown.splitlines()

    last_line: dict[str, int] = {}
    for index, line in enumerate(lines):
        match = _IMAGE_REF_RE.search(line)
        if match:
            last_line[match.group(1) or match.group(2)] = index

    kept = []
    for index, line in enumerate(lines):
        match = _IMAGE_REF_RE.search(line)
        if match and match.group(0) == line.strip():
            path = match.group(1) or match.group(2)
            if last_line[path] != index:
                continue
        kept.append(line)

    return re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip() + "\n"


def _validate_pdf(pdf_path: Path) -> None:
    """Check the input path points to an existing PDF file."""
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")
    if pdf_path.suffix.lower() != ".pdf":
        raise ValueError(f"Expected a .pdf file, got {pdf_path.suffix!r}: {pdf_path}")


def _clear_default_output_dir() -> None:
    """Remove previous generated results before a new default conversion."""
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for child in DEFAULT_OUTPUT_DIR.iterdir():
        if child.name == ".gitkeep":
            continue
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def convert_pdf_to_markdown(
    pdf_path: Path | str,
    output_dir: Path | str | None = None,
    hybrid: str = DEFAULT_HYBRID_BACKEND,
    hybrid_mode: str | None = None,
    hybrid_url: str | None = None,
    use_struct_tree: bool = False,
    quiet: bool = True,
) -> str:
    """Convert a single PDF into Markdown text.

    Hybrid mode is the default: start the backend first with::

        opendataloader-pdf-hybrid --port 5002

    Pass ``hybrid="off"`` for local-only processing (no backend service).
    Set ``hybrid_mode="full"`` to route every page to the backend —
    required for scanned PDFs (OCR) and enrichments such as formulas.

    Args:
        pdf_path: Path to the input PDF file.
        output_dir: Directory for the generated ``<stem>.md`` file.
            Defaults to the repository's ``generated_markdown`` directory.
        hybrid: Hybrid backend name. Values: "off", "docling-fast",
            "hancom-ai". Defaults to "docling-fast".
        hybrid_mode: Hybrid triage mode. Values: "auto" (default,
            dynamic triage), "full" (skip triage, all pages to backend).
        hybrid_url: Backend URL override (default http://localhost:5002).
        use_struct_tree: Prefer the PDF's native structure tags. Takes
            precedence over hybrid — the backend is not called.
        quiet: Suppress the JVM CLI console output.

    Returns:
        The generated Markdown text. Duplicated image references (the
        same figure emitted both at the document head and inline) are
        collapsed to their last occurrence.

    Raises:
        FileNotFoundError: If the PDF does not exist or Java is missing.
        ValueError: If ``pdf_path`` is not a .pdf file.
        HybridBackendError: If the hybrid backend is unreachable or the
            conversion fails.
    """
    pdf_path = Path(pdf_path)
    _validate_pdf(pdf_path)

    backend_url = hybrid_url or DEFAULT_HYBRID_URL
    if hybrid != "off" and not use_struct_tree and not is_backend_reachable(backend_url):
        raise HybridBackendError(
            f"Hybrid backend is not reachable at {backend_url}. "
            'Start it with: opendataloader-pdf-hybrid --port 5002 '
            '(or pass hybrid="off" for local-only processing).'
        )

    if output_dir is None:
        _clear_default_output_dir()

    out_dir = Path(output_dir) if output_dir is not None else DEFAULT_OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    context = nullcontext(out_dir)

    try:
        with context as work_dir:
            opendataloader_pdf.convert(
                input_path=str(pdf_path),
                output_dir=str(work_dir),
                format="markdown",
                hybrid=hybrid,
                hybrid_mode=hybrid_mode,
                hybrid_url=hybrid_url,
                use_struct_tree=use_struct_tree,
                quiet=quiet,
            )
            markdown_path = Path(work_dir) / f"{pdf_path.stem}.md"
            if not markdown_path.exists():
                raise RuntimeError(
                    "Conversion produced no Markdown file; expected "
                    f"{markdown_path}"
                )
            markdown_text = _deduplicate_image_references(
                markdown_path.read_text(encoding="utf-8")
            )
            markdown_path.write_text(markdown_text, encoding="utf-8")
            return markdown_text
    except subprocess.CalledProcessError as exc:
        raise HybridBackendError(f"PDF conversion failed: {exc}") from exc
    except FileNotFoundError as exc:
        raise FileNotFoundError(
            "The 'java' command was not found. Install JDK 11+ "
            "(https://adoptium.net) — opendataloader-pdf runs a JVM."
        ) from exc
