"""Tests for reference-list extraction."""

import json

from parser.opendataloader_adapter import (
    ConvertedDocument,
    DocumentElement,
    load_opendataloader_json,
)
from parser.reference_json_extractor import (
    LayoutReferenceCandidate,
    PDFTextLine,
    _layout_candidates_are_better,
    _needs_hanging_indent_fallback,
    detect_reference_family,
    detect_reference_style,
    extract_references_from_document,
    find_reference_section,
    parse_reference_metadata,
    reference_list_to_json,
    split_hanging_indent_lines,
    split_reference_entries,
)


def element(
    content: str,
    page: int,
    element_type: str = "paragraph",
    element_id: str = "test",
    bbox: tuple[float, float, float, float] = (
        72.0,
        100.0,
        280.0,
        120.0,
    ),
) -> DocumentElement:
    """Create a document element for unit tests."""

    return DocumentElement(
        element_id=element_id,
        element_type=element_type,
        content=content,
        page=page,
        bbox=bbox,
    )


def sample_document(
    elements: list[DocumentElement],
) -> ConvertedDocument:
    """Create a converted document for unit tests."""

    return ConvertedDocument(
        file_name="sample.pdf",
        title="Example Paper",
        author="Example Author",
        page_count=10,
        elements=elements,
    )


class TestFindReferenceSection:
    def test_finds_references_heading(self):
        document = sample_document(
            [
                element("Introduction", 1, "heading"),
                element("Paper content.", 1),
                element("References", 8, "heading"),
                element("[1] First example reference.", 8),
                element("[2] Second example reference.", 8),
            ]
        )

        section = find_reference_section(document)

        assert section is not None
        assert section.page == 8
        assert section.heading == "References"

    def test_accepts_bibliography_heading(self):
        document = sample_document(
            [
                element("Bibliography", 9, "heading"),
                element("[1] First example reference.", 9),
                element("[2] Second example reference.", 9),
            ]
        )

        section = find_reference_section(document)

        assert section is not None
        assert section.page == 9
        assert section.heading == "Bibliography"

    def test_accepts_unnumbered_author_year_references(self):
        document = sample_document(
            [
                element("References", 9, "paragraph"),
                element(
                    "Smith, J. A. (2022). A useful paper. Journal.",
                    9,
                ),
                element(
                    "World Health Organization. (2023). A report.",
                    9,
                ),
            ]
        )

        section = find_reference_section(document)

        assert section is not None
        assert section.heading == "References"

    def test_does_not_match_sentence_containing_references(self):
        document = sample_document(
            [
                element(
                    "Additional references are available online.",
                    7,
                    "paragraph",
                )
            ]
        )

        assert find_reference_section(document) is None

    def test_recovers_uppercase_heading_merged_into_previous_column(self):
        document = sample_document(
            [
                element(
                    "The final paragraph ends here. REFERENCES",
                    9,
                    "paragraph",
                ),
                element("[1] First example reference.", 9, "list item"),
                element("[2] Second example reference.", 9, "list item"),
            ]
        )

        section = find_reference_section(document)

        assert section is not None
        assert section.heading == "REFERENCES"
        assert section.body_prefix == "The final paragraph ends here."

    def test_prefers_real_heading_over_table_column(self):
        document = sample_document(
            [
                element("Reference", 7, "paragraph"),
                element("[40] Table row content.", 7),
                element("[42] Another table row.", 7),
                element("References", 9, "heading"),
                element("[1] First real reference.", 9),
                element("[2] Second real reference.", 9),
            ]
        )

        section = find_reference_section(document)

        assert section is not None
        assert section.heading == "References"
        assert section.page == 9


class TestSplitReferenceEntries:
    def test_splits_bracket_numbered_references(self):
        elements = [
            element("[1] First reference.", 8),
            element("Continuation of first reference.", 8),
            element("[2] Second reference.", 8),
        ]

        entries = split_reference_entries(elements)

        assert len(entries) == 2
        assert entries[0].text == ("[1] First reference. Continuation of first reference.")
        assert entries[1].text == "[2] Second reference."

    def test_splits_plain_numbered_references(self):
        elements = [
            element("1. First reference.", 8),
            element("2. Second reference.", 8),
        ]

        entries = split_reference_entries(elements)

        assert len(entries) == 2
        assert entries[0].text == "1. First reference."
        assert entries[1].text == "2. Second reference."

    def test_keeps_unnumbered_list_item_as_cross_column_continuation(self):
        elements = [
            element(
                "20. Obaid, L.: Spatiotemporal analysis using gis",
                8,
                "list item",
                bbox=(51.0, 75.0, 289.0, 95.0),
            ),
            element(
                "in Sharjah, UAE. Journal 18 (2024).",
                8,
                "list item",
                bbox=(322.0, 713.0, 544.0, 732.0),
            ),
            element(
                "21. Next, A.: Following reference.",
                8,
                "list item",
                bbox=(306.0, 663.0, 544.0, 712.0),
            ),
        ]

        entries = split_reference_entries(elements, style="plain-numbered")

        assert len(entries) == 2
        assert entries[0].text.endswith("in Sharjah, UAE. Journal 18 (2024).")
        assert entries[1].text.startswith("21.")

    def test_keeps_numbered_reference_continuation_across_pages(self):
        elements = [
            element("1. First reference begins.", 8),
            element("It continues on the next page.", 9),
            element("2. Second reference.", 9),
        ]

        entries = split_reference_entries(elements, style="plain-numbered")

        assert len(entries) == 2
        assert entries[0].pages == [8, 9]
        assert entries[0].text.endswith("continues on the next page.")

    def test_ignores_unnumbered_text_before_first_numbered_entry(self):
        elements = [
            element("Journal running header", 8),
            element("1. First reference.", 8),
            element("2. Second reference.", 8),
        ]

        entries = split_reference_entries(elements, style="plain-numbered")

        assert len(entries) == 2
        assert entries[0].text == "1. First reference."

    def test_splits_multiple_references_in_one_element(self):
        elements = [
            element(
                "[1] First reference.\n[2] Second reference.",
                8,
            )
        ]

        entries = split_reference_entries(elements)

        assert len(entries) == 2
        assert entries[0].text.startswith("[1]")
        assert entries[1].text.startswith("[2]")

    def test_splits_apa_references_and_keeps_continuation(self):
        elements = [
            element(
                "Smith, J. A. (2022). A useful paper. Journal.",
                8,
                bbox=(51.0, 700.0, 289.0, 730.0),
            ),
            element(
                "https://doi.org/10.1000/example",
                8,
                bbox=(68.0, 680.0, 289.0, 699.0),
            ),
            element(
                "World Health Organization. (n.d.). A report.",
                8,
                bbox=(51.0, 650.0, 289.0, 679.0),
            ),
        ]

        entries = split_reference_entries(
            elements,
            style="author-year-parenthesized",
        )

        assert len(entries) == 2
        assert entries[0].text.endswith("https://doi.org/10.1000/example")
        assert entries[1].text.startswith("World Health Organization")

    def test_splits_apa_reference_without_an_author(self):
        elements = [
            element("Smith, J. (2022). An authored work.", 8),
            element("A handbook of examples. (2023). Example Press.", 8),
        ]

        entries = split_reference_entries(
            elements,
            style="author-year-parenthesized",
        )

        assert len(entries) == 2
        assert entries[1].text.startswith("A handbook of examples")

    def test_splits_two_author_year_entries_merged_in_one_element(self):
        elements = [
            element(
                "Sun LQ, Guo W (2017) A pilot test. Geotext Geomembr. "
                "https://doi.org/10.1016/example Tang M, Shang JQ (2000) "
                "Vacuum consolidation. Journal 2:6-9",
                8,
            )
        ]

        entries = split_reference_entries(
            elements,
            style="author-year-inline",
        )

        assert len(entries) == 2
        assert entries[0].text.startswith("Sun LQ")
        assert entries[0].text.endswith("https://doi.org/10.1016/example")
        assert entries[1].text.startswith("Tang M")

    def test_splits_leading_continuation_from_following_apa_reference(self):
        elements = [
            element(
                "Previous reference continuation. Beta, B. (2021). A complete new reference.",
                8,
            )
        ]

        entries = split_reference_entries(
            elements,
            style="author-year-parenthesized",
        )

        assert len(entries) == 2
        assert entries[0].text == "Previous reference continuation."
        assert entries[1].text.startswith("Beta, B. (2021)")

    def test_restores_two_column_reading_order(self):
        elements = [
            element(
                "Right A RA (2020) First right-column reference.",
                8,
                bbox=(306.0, 700.0, 544.0, 730.0),
            ),
            element(
                "Left B LB (2019) Second left-column reference.",
                8,
                bbox=(51.0, 650.0, 289.0, 680.0),
            ),
            element(
                "Left A LA (2018) First left-column reference.",
                8,
                bbox=(51.0, 700.0, 289.0, 730.0),
            ),
            element(
                "Right B RB (2021) Second right-column reference.",
                8,
                bbox=(306.0, 650.0, 544.0, 680.0),
            ),
        ]

        entries = split_reference_entries(
            elements,
            style="author-year-inline",
        )

        assert [entry.text.split()[0] for entry in entries] == [
            "Left",
            "Left",
            "Right",
            "Right",
        ]


class TestDetectReferenceStyle:
    def test_detects_bracket_numbered_style(self):
        elements = [
            element("[1] First.", 8),
            element("[2] Second.", 8),
        ]

        assert detect_reference_style(elements) == "bracket-numbered"

    def test_detects_plain_numbered_style(self):
        elements = [
            element("1. First.", 8),
            element("2. Second.", 8),
        ]

        assert detect_reference_style(elements) == "plain-numbered"

    def test_detects_author_year_style(self):
        elements = [
            element("Bao SF, Mo HH (2014) A paper.", 8),
            element("Chai JC, Carter JP (2006) Another paper.", 8),
        ]

        assert detect_reference_style(elements) == "author-year-inline"


class TestReferenceMetadataParsing:
    def test_parses_apa_7_metadata(self):
        metadata = parse_reference_metadata(
            "Smith, J. A., & Brown, T. B. (2022). Article title: A subtitle. "
            "Journal of Tests, 10(2), 1-9. https://doi.org/10.1234/test.1"
        )

        assert metadata.authors == ["Smith, J. A.", "Brown, T. B."]
        assert metadata.year == 2022
        assert metadata.title == "Article title: A subtitle"
        assert metadata.venue == "Journal of Tests"
        assert metadata.doi == "10.1234/test.1"

    def test_parses_apa_no_date_with_null_year(self):
        metadata = parse_reference_metadata(
            "World Health Organization. (n.d.). Health guidance. WHO Press."
        )

        assert metadata.authors == ["World Health Organization"]
        assert metadata.year is None
        assert metadata.title == "Health guidance"
        assert metadata.venue == "WHO Press"
        assert metadata.doi is None

    def test_tolerates_lowercase_apa_initials_from_pdf_extraction(self):
        metadata = parse_reference_metadata(
            "Fu, T.-y., Lee, W.-C., & Lei, Z. (2017). Hin2vec methods. "
            "Proceedings of Testing."
        )

        assert metadata.authors == ["Fu, T.-y.", "Lee, W.-C.", "Lei, Z."]
        assert metadata.year == 2017
        assert metadata.title == "Hin2vec methods"

    def test_does_not_split_apa_title_at_an_acronym(self):
        metadata = parse_reference_metadata(
            "Smith, J. (2022). Use of U.S. health data in practice. Journal of Tests."
        )

        assert metadata.title == "Use of U.S. health data in practice"
        assert metadata.venue == "Journal of Tests"

    def test_parses_ieee_metadata(self):
        metadata = parse_reference_metadata(
            "[1] J. A. Smith and T. Brown, \u201cAn IEEE paper title,\u201d "
            "IEEE Transactions on Testing, vol. 10, no. 2, pp. 1-9, 2021, "
            "doi: 10.1109/TEST.2021.12345."
        )

        assert metadata.authors == ["J. A. Smith", "T. Brown"]
        assert metadata.year == 2021
        assert metadata.title == "An IEEE paper title"
        assert metadata.venue == "IEEE Transactions on Testing"
        assert metadata.doi == "10.1109/TEST.2021.12345"

    def test_parses_ieee_metadata_with_pdf_extraction_quote_noise(self):
        metadata = parse_reference_metadata(
            "[1] J. Haberman and D. Whitney, ªSeeing the mean: Ensemble coding "
            "for sets of faces,º Journal of Experimental Psychology, vol. 35, "
            "no. 3, pp. 718-734, 2009. doi: 10.1037/a0013899."
        )

        assert metadata.authors == ["J. Haberman", "D. Whitney"]
        assert metadata.year == 2009
        assert metadata.title == "Seeing the mean: Ensemble coding for sets of faces"
        assert metadata.venue == "Journal of Experimental Psychology"
        assert metadata.doi == "10.1037/a0013899"

    def test_leaves_vancouver_nlm_metadata_null(self):
        metadata = parse_reference_metadata(
            "2. Smith JA, Brown TB. A Vancouver article title. "
            "J Test Med. 2020;10(2):1-9. doi:10.1000/test.2"
        )

        assert metadata.authors is None
        assert metadata.year is None
        assert metadata.title is None
        assert metadata.venue is None
        assert metadata.doi is None

    def test_returns_null_metadata_for_an_unmatched_format(self):
        metadata = parse_reference_metadata(
            "[3] D.M. Chiorean, et al., New insights into genetics, "
            "Diagn. 13 (2023)."
        )

        assert metadata.authors is None
        assert metadata.year is None
        assert metadata.title is None
        assert metadata.venue is None
        assert metadata.doi is None

    def test_does_not_misclassify_springer_reference_as_apa(self):
        metadata = parse_reference_metadata(
            "1. Amiri, A.M., Naderi, K.: Evaluating traffic safety. "
            "J. Transport Health 20, 101010 (2021). "
            "https://doi.org/10.1016/j.jth.2021.101010"
        )

        assert metadata.authors is None
        assert metadata.year is None
        assert metadata.title is None
        assert metadata.venue is None
        assert metadata.doi is None


class TestEndToEndExtraction:
    def test_keeps_every_entry_and_serializes_supported_or_null_metadata(self):
        document = sample_document(
            [
                element("References", 8, "heading"),
                element(
                    "[1] J. A. Smith, \u201cAn IEEE paper title,\u201d Journal of Tests, "
                    "vol. 2, pp. 1-9, 2021.",
                    8,
                ),
                element("[2] An irregular reference that does not match a parser.", 8),
            ]
        )

        result = extract_references_from_document(document)
        references = json.loads(reference_list_to_json(result))["references"]

        assert len(references) == 2
        assert references[0]["title"] == "An IEEE paper title"
        assert references[0]["authors"] == ["J. A. Smith"]
        assert references[1] == {
            "raw_text": "[2] An irregular reference that does not match a parser.",
            "authors": None,
            "year": None,
            "title": None,
            "venue": None,
            "doi": None,
        }

    def test_recovers_later_column_references_ordered_before_heading(self):
        document = sample_document(
            [
                element("Introduction", 1, "heading"),
                # A layout engine may emit the top of the right column before
                # reaching a References heading low in the left column.
                element(
                    "[3] Third reference. Journal, 2021.",
                    9,
                    "list item",
                    bbox=(308.0, 700.0, 557.0, 730.0),
                ),
                element(
                    "[4] Fourth reference. Journal, 2021.",
                    9,
                    "list item",
                    bbox=(308.0, 660.0, 557.0, 690.0),
                ),
                element(
                    "References",
                    9,
                    "heading",
                    bbox=(37.0, 230.0, 90.0, 250.0),
                ),
                element(
                    "[1] First reference. Journal, 2021.",
                    9,
                    "list item",
                    bbox=(42.0, 200.0, 289.0, 225.0),
                ),
                element(
                    "[2] Second reference. Journal, 2021.",
                    9,
                    "list item",
                    bbox=(42.0, 160.0, 289.0, 190.0),
                ),
                element(
                    "[5] Fifth reference. Journal, 2021.",
                    10,
                    "list item",
                    bbox=(42.0, 700.0, 289.0, 730.0),
                ),
                element(
                    "[6] Sixth reference. Journal, 2021.",
                    10,
                    "list item",
                    bbox=(308.0, 700.0, 557.0, 730.0),
                ),
            ]
        )

        result = extract_references_from_document(document)

        assert [reference.number for reference in result.references] == [
            1,
            2,
            3,
            4,
            5,
            6,
        ]
        assert not any("discontinuous" in warning for warning in result.warnings)

    def test_warns_when_numbered_references_have_a_gap(self):
        document = sample_document(
            [
                element("References", 8, "heading"),
                element("[1] First reference. Journal, 2021.", 8),
                element("[3] Third reference. Journal, 2021.", 8),
            ]
        )

        result = extract_references_from_document(document)

        assert any(
            "Reference numbering is discontinuous (missing 2)." == warning
            for warning in result.warnings
        )

    def test_warns_when_numbered_references_do_not_start_at_one(self):
        document = sample_document(
            [
                element("References", 8, "heading"),
                element("[3] Third reference. Journal, 2021.", 8),
                element("[4] Fourth reference. Journal, 2021.", 8),
            ]
        )

        result = extract_references_from_document(document)

        assert any(
            "Reference numbering is discontinuous (missing 1-2)." == warning
            for warning in result.warnings
        )

    def test_preserves_raw_text_number_and_pages(self):
        document = sample_document(
            [
                element("Introduction", 1, "heading"),
                element("Body text.", 1),
                element("References", 8, "heading"),
                element(
                    '[1] A. Author, "A useful paper," Journal, 2021. doi:10.1234/example.5678',
                    8,
                ),
                element(
                    "[2] B. Author. Another useful paper. Conference, 2022. "
                    "https://example.org/paper",
                    9,
                ),
            ]
        )

        result = extract_references_from_document(document)

        assert result.heading == "References"
        assert result.start_page == 8
        assert result.end_page == 9
        assert result.style == "bracket-numbered"
        assert len(result.references) == 2

        first = result.references[0]

        assert first.number == 1
        assert first.raw_text.endswith("doi:10.1234/example.5678")
        assert first.page_start == 8
        assert first.page_end == 8

        second = result.references[1]

        assert second.number == 2
        assert second.raw_text.endswith("https://example.org/paper")
        assert second.page_start == 9
        assert second.page_end == 9

    def test_stops_at_appendix(self):
        document = sample_document(
            [
                element("References", 8, "heading"),
                element("[1] First reference. Journal, 2021.", 8),
                element("Appendix", 9, "heading"),
                element("[2] This is not a reference.", 9),
            ]
        )

        result = extract_references_from_document(document)

        assert result.heading == "References"
        assert len(result.references) == 1
        assert result.references[0].number == 1
        assert "This is not a reference" not in result.references[0].raw_text

    def test_stops_at_publisher_note_paragraph(self):
        document = sample_document(
            [
                element("References", 8, "heading"),
                element("1. First reference. Journal (2021).", 8),
                element("2. Second reference. Journal (2022).", 8),
                element(
                    "Publisher’s Note Springer Nature remains neutral with "
                    "regard to jurisdictional claims.",
                    8,
                    "paragraph",
                ),
                element(
                    "Springer Nature or its licensor holds exclusive rights.",
                    8,
                    "paragraph",
                ),
            ]
        )

        result = extract_references_from_document(document)

        assert len(result.references) == 2
        assert "Publisher" not in result.references[-1].raw_text
        assert "licensor" not in result.references[-1].raw_text

    def test_extracts_unnumbered_author_year_references(self):
        document = sample_document(
            [
                element("References", 8, "paragraph"),
                element(
                    "Bao SF, Mo HH (2014) First paper. Journal 1:1-5",
                    8,
                    bbox=(51.0, 700.0, 289.0, 730.0),
                ),
                element(
                    "Chai JC, Carter JP (2006) Second paper. Journal 2:6-9",
                    8,
                    bbox=(51.0, 660.0, 289.0, 690.0),
                ),
            ]
        )

        result = extract_references_from_document(document)

        assert result.style == "author-year-inline"
        assert result.style_confidence >= 0.5
        assert len(result.references) == 2
        assert result.references[0].raw_text.startswith("Bao SF")

    def test_returns_warning_when_heading_missing(self):
        document = sample_document(
            [
                element("Introduction", 1, "heading"),
                element("Body text.", 1),
            ]
        )

        result = extract_references_from_document(document)

        assert result.references == []
        assert result.heading is None
        assert result.start_page is None
        assert result.warnings
        assert result.warnings[0] == ("Reference-list heading was not found.")
        assert json.loads(reference_list_to_json(result))["warnings"] == result.warnings

    def test_result_is_valid_json(self):
        document = sample_document(
            [
                element("References", 8, "heading"),
                element(
                    "[1] A. Author. Example title. 2021.",
                    8,
                ),
                element(
                    "[2] B. Author. Another title. 2022. https://example.org/paper",
                    8,
                ),
            ]
        )

        result = extract_references_from_document(document)
        serialized = reference_list_to_json(result)
        parsed = json.loads(serialized)

        assert parsed == {
            "source_file": "sample.pdf",
            "references": [
                {
                    "raw_text": "[1] A. Author. Example title. 2021.",
                    "authors": None,
                    "year": None,
                    "title": None,
                    "venue": None,
                    "doi": None,
                },
                {
                    "raw_text": (
                        "[2] B. Author. Another title. 2022. https://example.org/paper"
                    ),
                    "authors": None,
                    "year": None,
                    "title": None,
                    "venue": None,
                    "doi": None,
                },
            ],
        }


class TestHangingIndentFallback:
    def test_detects_overmerged_apa_elements(self):
        document = sample_document(
            [
                element("References", 8, "heading"),
                element(
                    "Alpha, A. (2020). First. Beta, B. (2021). Second. Gamma, G. (2022). Third.",
                    8,
                ),
                element(
                    "Delta, D. (2023). Fourth. Echo, E. (2024). Fifth. Foxtrot, F. (2025). Sixth.",
                    8,
                ),
            ]
        )
        result = extract_references_from_document(document)

        assert _needs_hanging_indent_fallback(document, result)

    def test_accepts_only_larger_coherent_layout_result(self):
        existing = extract_references_from_document(
            sample_document(
                [
                    element("References", 8, "heading"),
                    element("Alpha, A. (2020). First.", 8),
                    element("Beta, B. (2021). Second.", 8),
                ]
            )
        )
        candidates = [
            LayoutReferenceCandidate("Alpha, A. (2020). First."),
            LayoutReferenceCandidate("Beta, B. (2021). Second."),
            LayoutReferenceCandidate("Gamma, G. (2022). Third."),
        ]

        assert _layout_candidates_are_better(candidates, existing)
        assert not _layout_candidates_are_better(candidates[:2], existing)


def test_preserves_line_boundaries_and_layout_metadata(tmp_path):
    source = tmp_path / "converted.json"
    source.write_text(
        json.dumps(
            {
                "file name": "paper.pdf",
                "number of pages": 2,
                "kids": [
                    {
                        "type": "paragraph",
                        "content": "Smith, J. (2022). Title.\n   Continued URL.",
                        "page number": 2,
                        "bounding box": [51, 100, 289, 130],
                        "font": "Example",
                        "font size": "9.5",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    document = load_opendataloader_json(source)

    assert document.file_name == "paper.pdf"
    assert document.page_count == 2
    assert len(document.elements) == 1
    assert document.elements[0].content == ("Smith, J. (2022). Title.\nContinued URL.")
    assert document.elements[0].bbox == (51.0, 100.0, 289.0, 130.0)
    assert document.elements[0].font_size == 9.5


def test_inherits_page_and_does_not_duplicate_nested_text(tmp_path):
    source = tmp_path / "nested.json"
    source.write_text(
        json.dumps(
            {
                "number of pages": 1,
                "kids": [
                    {
                        "type": "page",
                        "page number": 1,
                        "kids": [
                            {
                                "type": "paragraph",
                                "content": "Complete paragraph.",
                                "kids": [
                                    {"type": "span", "content": "Complete"},
                                    {"type": "span", "content": "paragraph."},
                                ],
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    document = load_opendataloader_json(source)

    assert [element.content for element in document.elements] == ["Complete paragraph."]
    assert document.elements[0].page == 1


def pdf_line(
    text: str,
    page: int,
    x: float,
    y: float,
) -> PDFTextLine:
    return PDFTextLine(text=text, page=page, bbox=(x, y, 500.0, y + 10.0))


def test_splits_hanging_indent_references():
    lines = [
        pdf_line("Alpha, A. (2020). First", 8, 39.0, 100.0),
        pdf_line("reference title. Journal.", 8, 51.0, 112.0),
        pdf_line("Beta, B. (2021). Second", 8, 39.0, 136.0),
        pdf_line("reference title. Journal.", 8, 51.0, 148.0),
    ]

    candidates = split_hanging_indent_lines(lines)

    assert [candidate.text for candidate in candidates] == [
        "Alpha, A. (2020). First reference title. Journal.",
        "Beta, B. (2021). Second reference title. Journal.",
    ]


def test_splits_two_column_hanging_indent_references():
    lines = [
        pdf_line("Left A, A. (2020). First", 8, 39.0, 100.0),
        pdf_line("left-column reference.", 8, 51.0, 112.0),
        pdf_line("Left B, B. (2021). Second", 8, 39.0, 136.0),
        pdf_line("left-column reference.", 8, 51.0, 148.0),
        pdf_line("Right A, A. (2022). First", 8, 306.0, 100.0),
        pdf_line("right-column reference.", 8, 318.0, 112.0),
        pdf_line("Right B, B. (2023). Second", 8, 306.0, 136.0),
        pdf_line("right-column reference.", 8, 318.0, 148.0),
    ]

    candidates = split_hanging_indent_lines(lines)

    assert [candidate.text for candidate in candidates] == [
        "Left A, A. (2020). First left-column reference.",
        "Left B, B. (2021). Second left-column reference.",
        "Right A, A. (2022). First right-column reference.",
        "Right B, B. (2023). Second right-column reference.",
    ]


def test_restores_column_order_before_splitting_hanging_indents():
    lines = [
        pdf_line("Left A, A. (2020). First", 8, 39.0, 100.0),
        pdf_line("Right A, A. (2022). Third", 8, 306.0, 100.0),
        pdf_line("left-column reference.", 8, 51.0, 112.0),
        pdf_line("right-column reference.", 8, 318.0, 112.0),
        pdf_line("Left B, B. (2021). Second", 8, 39.0, 136.0),
        pdf_line("Right B, B. (2023). Fourth", 8, 306.0, 136.0),
        pdf_line("left-column reference.", 8, 51.0, 148.0),
        pdf_line("right-column reference.", 8, 318.0, 148.0),
    ]

    candidates = split_hanging_indent_lines(lines)

    assert [candidate.text.split(",", 1)[0] for candidate in candidates] == [
        "Left A",
        "Left B",
        "Right A",
        "Right B",
    ]


def test_keeps_cross_page_continuation_with_previous_reference():
    lines = [
        pdf_line("Alpha, A. (2020). First reference.", 8, 39.0, 100.0),
        pdf_line("Its continuation", 8, 51.0, 112.0),
        pdf_line("continues on the next page.", 9, 51.0, 50.0),
        pdf_line("Beta, B. (2021). Second reference.", 9, 39.0, 74.0),
        pdf_line("Second continuation.", 9, 51.0, 86.0),
    ]

    candidates = split_hanging_indent_lines(lines)

    assert len(candidates) == 2
    assert candidates[0].pages == [8, 9]
    assert candidates[0].text.endswith("continues on the next page.")
    assert candidates[1].pages == [9]


def test_preserves_hyphen_without_adding_line_break_space():
    lines = [
        pdf_line("Alpha, A. (2020). Knowledge-", 8, 39.0, 100.0),
        pdf_line("based innovation.", 8, 51.0, 112.0),
        pdf_line("Beta, B. (2021). Another", 8, 39.0, 136.0),
        pdf_line("reference.", 8, 51.0, 148.0),
    ]

    candidates = split_hanging_indent_lines(lines)

    assert "Knowledge-based" in candidates[0].text


def test_rejects_lines_without_hanging_indent_evidence():
    lines = [
        pdf_line("Alpha, A. (2020). First reference.", 8, 39.0, 100.0),
        pdf_line("Beta, B. (2021). Second reference.", 8, 39.0, 124.0),
        pdf_line("Gamma, G. (2022). Third reference.", 8, 39.0, 148.0),
        pdf_line("Delta, D. (2023). Fourth reference.", 8, 39.0, 172.0),
    ]

    assert split_hanging_indent_lines(lines) == []


def detect_family(*texts: str):
    return detect_reference_family([element(text, 8) for text in texts])


def test_detects_bracket_numbered_family():
    result = detect_family(
        "[1] A. Author, A paper, 2022.",
        "[2] B. Author, Another paper, 2023.",
    )

    assert result.family == "bracket-numbered"
    assert result.confidence >= 0.9


def test_detects_plain_numbered_family():
    result = detect_family(
        "1. A. Author, A paper, 2022.",
        "2) B. Author, Another paper, 2023.",
    )

    assert result.family == "plain-numbered"


def test_detects_apa_parenthesized_family():
    result = detect_family(
        "Smith, J. A., & Doe, B. (2022). A useful paper. Journal, 2(1), 1-9.",
        "World Health Organization. (n.d.). Health guidance. https://example.org",
        "Example report. (2023a). Publisher.",
    )

    assert result.family == "author-year-parenthesized"
    assert result.evidence["parenthesized_date_ratio"] == 1.0


def test_detects_springer_author_year_family():
    result = detect_family(
        "Bao SF, Mo HH, Dong ZL, Chen PS (2014) Increment calculation of soil strength.",
        "Chai JC, Carter JP, Hayashi S (2006) Vacuum consolidation and loading.",
        "Ming JP, Zhao WB (2005) Study on groundwater level.",
    )

    assert result.family == "author-year-inline"


def test_detects_author_title_family_without_years():
    result = detect_family(
        "Smith, John. The Example Book. Example Press.",
        "Taylor, Anne. Another Example. Sample Journal.",
    )

    assert result.family == "author-title"


def test_ambiguous_content_remains_unknown():
    result = detect_family(
        "Documentation available from the project website.",
        "A second irregular source without recognizable structure.",
    )

    assert result.family == "unknown-unnumbered"
    assert result.confidence < 0.5
