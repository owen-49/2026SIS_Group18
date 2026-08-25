"""Tests for reference-format family detection."""

from dataclasses import dataclass

from reference_style import detect_reference_family


@dataclass
class Element:
    content: str


def detect(*texts: str):
    return detect_reference_family([Element(text) for text in texts])


def test_detects_bracket_numbered_family():
    result = detect(
        "[1] A. Author, A paper, 2022.",
        "[2] B. Author, Another paper, 2023.",
    )

    assert result.family == "bracket-numbered"
    assert result.confidence >= 0.9


def test_detects_plain_numbered_family():
    result = detect(
        "1. A. Author, A paper, 2022.",
        "2) B. Author, Another paper, 2023.",
    )

    assert result.family == "plain-numbered"


def test_detects_apa_parenthesized_family():
    result = detect(
        "Smith, J. A., & Doe, B. (2022). A useful paper. Journal, 2(1), 1-9.",
        "World Health Organization. (n.d.). Health guidance. https://example.org",
        "Example report. (2023a). Publisher.",
    )

    assert result.family == "author-year-parenthesized"
    assert result.evidence["parenthesized_date_ratio"] == 1.0


def test_detects_springer_author_year_family():
    result = detect(
        "Bao SF, Mo HH, Dong ZL, Chen PS (2014) Increment calculation of soil strength.",
        "Chai JC, Carter JP, Hayashi S (2006) Vacuum consolidation and loading.",
        "Ming JP, Zhao WB (2005) Study on groundwater level.",
    )

    assert result.family == "author-year-inline"


def test_detects_author_title_family_without_years():
    result = detect(
        "Smith, John. The Example Book. Example Press.",
        "Taylor, Anne. Another Example. Sample Journal.",
    )

    assert result.family == "author-title"


def test_ambiguous_content_remains_unknown():
    result = detect(
        "Documentation available from the project website.",
        "A second irregular source without recognizable structure.",
    )

    assert result.family == "unknown-unnumbered"
    assert result.confidence < 0.5
