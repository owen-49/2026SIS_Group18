"""Tests for normalizing OpenDataLoader JSON."""

import json

from opendataloader_adapter import load_opendataloader_json


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
    assert document.elements[0].content == (
        "Smith, J. (2022). Title.\nContinued URL."
    )
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

    assert [element.content for element in document.elements] == [
        "Complete paragraph."
    ]
    assert document.elements[0].page == 1
