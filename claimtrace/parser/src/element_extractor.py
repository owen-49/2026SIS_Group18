"""Semantic element extraction from academic PDFs.

Handles:
- Formula region detection and LaTeX restoration
- Table boundary detection
- Figure/caption pairing
"""

from dataclasses import dataclass
from pathlib import Path


@dataclass
class Formula:
    """A detected formula with position and optional LaTeX source."""

    latex: str | None
    bbox: tuple[float, float, float, float]
    page: int


@dataclass
class TableElement:
    """A detected table with structured data."""

    caption: str | None
    rows: list[list[str]]
    bbox: tuple[float, float, float, float]
    page: int


@dataclass
class FigureElement:
    """A detected figure with caption."""

    caption: str | None
    bbox: tuple[float, float, float, float]
    page: int


@dataclass
class SemanticElements:
    """All semantic elements extracted from a paper."""

    formulas: list[Formula]
    tables: list[TableElement]
    figures: list[FigureElement]


def extract_formulas(pdf_path: Path) -> list[Formula]:
    """Detect formula regions in a PDF.

    Strategy (v0.1): Identify regions with high density of math symbols
    or use image-based detection for rendered equations.
    Falls back to position-based heuristics for common math layouts.

    Args:
        pdf_path: Path to the PDF file.

    Returns:
        List of detected Formula objects.
    """
    # STUB — to be implemented with Nougat/Pix2Text in W2-W3
    # For Spike W1: return empty list, focus on text extraction first
    return []


def extract_tables(pdf_path: Path) -> list[TableElement]:
    """Extract tables from a PDF using pdfplumber.

    Args:
        pdf_path: Path to the PDF file.

    Returns:
        List of TableElement objects with extracted data.
    """
    import pdfplumber

    tables: list[TableElement] = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            found = page.extract_tables()
            for table_data in found:
                if not table_data:
                    continue
                tables.append(
                    TableElement(
                        caption=None,
                        rows=table_data,
                        bbox=page.bbox,
                        page=page_num,
                    )
                )
    return tables


def extract_figures(pdf_path: Path) -> list[FigureElement]:
    """Detect figure regions and pair with nearby captions.

    Strategy: Identify large image-only regions, then search for
    "Figure N:" or "Fig. N:" captions in nearby text blocks.

    Args:
        pdf_path: Path to the PDF file.

    Returns:
        List of FigureElement objects.
    """
    # STUB — to be implemented in W3-W4
    return []


def extract_all(pdf_path: Path) -> SemanticElements:
    """Run all element extractors on a PDF.

    Args:
        pdf_path: Path to the PDF file.

    Returns:
        SemanticElements containing all detected elements.
    """
    return SemanticElements(
        formulas=extract_formulas(pdf_path),
        tables=extract_tables(pdf_path),
        figures=extract_figures(pdf_path),
    )
