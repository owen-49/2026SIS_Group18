"""Tests for numbered in-text citation sentence extraction."""

import json

import pymupdf

from parser.citation_sentence_extractor import (
    citation_sentence_list_to_json,
    extract_citation_sentences_from_document,
    locate_citation_markers,
)
from parser.opendataloader_adapter import ConvertedDocument, DocumentElement


def element(
    content: str,
    page: int = 1,
    element_type: str = "paragraph",
    element_id: str = "body",
) -> DocumentElement:
    return DocumentElement(
        element_id=element_id,
        element_type=element_type,
        content=content,
        page=page,
        bbox=(50.0, 100.0, 280.0, 140.0),
    )


def document_with_body(body: list[DocumentElement], reference_count: int = 20):
    references = [
        element("References", 8, "heading", "references-heading"),
        *[
            element(f"[{number}] Example reference {number}.", 8, element_id=f"ref-{number}")
            for number in range(1, reference_count + 1)
        ],
    ]
    return ConvertedDocument(
        file_name="sample.pdf",
        title="Sample",
        author="Author",
        page_count=8,
        elements=[*body, *references],
    )


def test_extracts_complete_sentence_containing_citation():
    document = document_with_body(
        [
            element(
                "Background sentence. The proposed method improves accuracy [1]. "
                "Following sentence."
            )
        ]
    )

    result = extract_citation_sentences_from_document(document)

    assert len(result.sentences) == 1
    assert result.sentences[0].text == "The proposed method improves accuracy [1]."
    assert result.sentences[0].citation_ids == [1]


def test_keeps_full_sentence_when_citations_appear_mid_sentence():
    document = document_with_body(
        [
            element(
                "Resources include ClinVar [6], ClinGen [7], the Human Phenotype "
                "Ontology [8], and DisGeNet [9]."
            )
        ]
    )

    result = extract_citation_sentences_from_document(document)

    assert len(result.sentences) == 1
    assert result.sentences[0].text.endswith("DisGeNet [9].")
    assert result.sentences[0].citation_ids == [6, 7, 8, 9]


def test_supports_adjacent_grouped_and_ranged_citations():
    document = document_with_body(
        [
            element(
                "One finding supports the result [1][15]. Another finding has "
                "several sources [3, 4]. A final finding uses a range [5-7]."
            )
        ]
    )

    result = extract_citation_sentences_from_document(document)

    assert [sentence.citation_ids for sentence in result.sentences] == [
        [1, 15],
        [3, 4],
        [5, 6, 7],
    ]


def test_does_not_split_after_et_al_abbreviation():
    document = document_with_body(
        [
            element(
                "Schulte-Sasse et al. used a graph model to identify cancer genes [2]."
            )
        ]
    )

    result = extract_citation_sentences_from_document(document)

    assert len(result.sentences) == 1
    assert result.sentences[0].text.startswith("Schulte-Sasse et al.")


def test_does_not_split_on_version_number():
    document = document_with_body(
        [
            element(
                "Filtering used Seurat (v. 5.3.0) [4], and another established package."
            )
        ]
    )

    result = extract_citation_sentences_from_document(document)

    assert len(result.sentences) == 1
    assert result.sentences[0].text.startswith("Filtering used Seurat")


def test_rejects_numeric_interval_and_unknown_reference_number():
    document = document_with_body(
        [
            element(
                "A mask vector has a value in [0, 1] during model training. "
                "This otherwise valid prose cites a missing source [99]."
            )
        ]
    )

    result = extract_citation_sentences_from_document(document)

    assert result.sentences == []


def test_excludes_reference_list_and_non_prose_elements():
    body = [
        element("The prose contains a valid source [1].", element_id="prose"),
        element(
            "A mathematical equation with surrounding words [2].",
            element_type="formula",
            element_id="formula",
        ),
    ]
    document = document_with_body(body)

    result = extract_citation_sentences_from_document(document)

    assert len(result.sentences) == 1
    assert result.sentences[0].source_element_ids == ["prose"]
    assert all(not sentence.text.startswith("[1]") for sentence in result.sentences)


def test_repairs_line_wrap_hyphenation():
    document = document_with_body(
        [element("The model improves represen-\ntation quality [1].")]
    )

    result = extract_citation_sentences_from_document(document)

    assert result.sentences[0].text == "The model improves representation quality [1]."


def test_joins_sentence_split_across_paragraph_elements():
    document = document_with_body(
        [
            element(
                "Earlier context. Altered expression may affect abnormal",
                element_id="part-one",
            ),
            DocumentElement(
                element_id="part-two",
                element_type="paragraph",
                content="cells [4]. A later sentence.",
                page=1,
                bbox=(50.0, 70.0, 280.0, 95.0),
            ),
        ]
    )

    result = extract_citation_sentences_from_document(document)

    assert result.sentences[0].text == "Altered expression may affect abnormal cells [4]."
    assert result.sentences[0].source_element_ids == ["part-one", "part-two"]


def test_joins_cross_page_continuation_while_skipping_table_fragments():
    document = document_with_body(
        [
            DocumentElement(
                element_id="page-one",
                element_type="paragraph",
                content="Filtering used established packages [4], which were",
                page=1,
                bbox=(306.0, 45.0, 558.0, 120.0),
            ),
            DocumentElement(
                element_id="table-cell",
                element_type="paragraph",
                content="with each disease Jaccard index variants",
                page=2,
                bbox=(160.0, 300.0, 548.0, 340.0),
            ),
            DocumentElement(
                element_id="page-two",
                element_type="paragraph",
                content="used to create cell-type-specific co-expression networks.",
                page=2,
                bbox=(50.0, 230.0, 280.0, 290.0),
            ),
        ]
    )

    result = extract_citation_sentences_from_document(document)

    assert result.sentences[0].text == (
        "Filtering used established packages [4], which were used to create "
        "cell-type-specific co-expression networks."
    )
    assert result.sentences[0].page_end == 2


def test_json_contains_one_record_per_reference_link():
    document = document_with_body(
        [element("The result is supported by two sources [3, 4].")]
    )
    result = extract_citation_sentences_from_document(document)

    payload = json.loads(citation_sentence_list_to_json(result))

    assert [citation["citation_id"] for citation in payload["citations"]] == [3, 4]
    assert len({citation["sentence_id"] for citation in payload["citations"]}) == 1
    assert payload["citations"][0]["sentence"] == payload["citations"][1]["sentence"]
    assert payload["citations"][0]["locations"] == []
    assert "page_start" not in payload["citations"][0]
    assert "page_end" not in payload["citations"][0]
    assert "marker_start" not in payload["citations"][0]
    assert "marker_end" not in payload["citations"][0]


def test_attaches_searchable_citation_marker_location(tmp_path):
    pdf_path = tmp_path / "citation.pdf"
    pdf = pymupdf.open()
    page = pdf.new_page()
    page.insert_text(
        (72.0, 100.0),
        "The proposed method improves accuracy [1].",
    )
    pdf.save(pdf_path)
    pdf.close()

    document = document_with_body(
        [element("The proposed method improves accuracy [1].")]
    )
    result = extract_citation_sentences_from_document(document)

    locate_citation_markers(pdf_path, document, result)
    payload = json.loads(citation_sentence_list_to_json(result))

    location = payload["citations"][0]["locations"][0]
    assert location["page"] == 1
    assert "match_type" not in location
    assert location["bounding_boxes"]
    box = location["bounding_boxes"][0]
    assert box["x1"] - box["x0"] < 25


def test_returns_warning_when_numbered_reference_list_is_missing():
    document = ConvertedDocument(
        file_name="sample.pdf",
        title=None,
        author=None,
        page_count=2,
        elements=[element("A possible citation appears here [1].")],
    )

    result = extract_citation_sentences_from_document(document)

    assert result.sentences == []
    assert result.warnings
