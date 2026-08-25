"""Tests for the hanging-indent PDF line fallback."""

from reference_line_extractor import PDFTextLine, split_hanging_indent_lines


def line(
    text: str,
    page: int,
    x: float,
    y: float,
) -> PDFTextLine:
    return PDFTextLine(text=text, page=page, bbox=(x, y, 500.0, y + 10.0))


def test_splits_hanging_indent_references():
    lines = [
        line("Alpha, A. (2020). First", 8, 39.0, 100.0),
        line("reference title. Journal.", 8, 51.0, 112.0),
        line("Beta, B. (2021). Second", 8, 39.0, 136.0),
        line("reference title. Journal.", 8, 51.0, 148.0),
    ]

    candidates = split_hanging_indent_lines(lines)

    assert [candidate.text for candidate in candidates] == [
        "Alpha, A. (2020). First reference title. Journal.",
        "Beta, B. (2021). Second reference title. Journal.",
    ]


def test_keeps_cross_page_continuation_with_previous_reference():
    lines = [
        line("Alpha, A. (2020). First reference.", 8, 39.0, 100.0),
        line("Its continuation", 8, 51.0, 112.0),
        line("continues on the next page.", 9, 51.0, 50.0),
        line("Beta, B. (2021). Second reference.", 9, 39.0, 74.0),
        line("Second continuation.", 9, 51.0, 86.0),
    ]

    candidates = split_hanging_indent_lines(lines)

    assert len(candidates) == 2
    assert candidates[0].pages == [8, 9]
    assert candidates[0].text.endswith("continues on the next page.")
    assert candidates[1].pages == [9]


def test_preserves_hyphen_without_adding_line_break_space():
    lines = [
        line("Alpha, A. (2020). Knowledge-", 8, 39.0, 100.0),
        line("based innovation.", 8, 51.0, 112.0),
        line("Beta, B. (2021). Another", 8, 39.0, 136.0),
        line("reference.", 8, 51.0, 148.0),
    ]

    candidates = split_hanging_indent_lines(lines)

    assert "Knowledge-based" in candidates[0].text


def test_rejects_lines_without_hanging_indent_evidence():
    lines = [
        line("Alpha, A. (2020). First reference.", 8, 39.0, 100.0),
        line("Beta, B. (2021). Second reference.", 8, 39.0, 124.0),
        line("Gamma, G. (2022). Third reference.", 8, 39.0, 148.0),
        line("Delta, D. (2023). Fourth reference.", 8, 39.0, 172.0),
    ]

    assert split_hanging_indent_lines(lines) == []
