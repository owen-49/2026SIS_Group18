"""Manuscript-scoped reference integration; no network or model downloads."""

from uuid import uuid4

import pytest
from backend.src.config import get_settings
from backend.src.models import ComparisonStatus
from backend.src.services import citation_comparison_service, engine_adapter, source_locator
from backend.src.services.source_locator import look_up_citation
from backend.src.storage.reference_store import (
    StoredReference,
    StoredReferenceList,
    save_references,
)
from test_citation_comparison_api import FakeLLM, FakeRetriever
from test_source_locator import _add_bibliography, _add_source_pdf, _entry


def manuscript(text="A retrieval method improves citation checking [7].", number=7):
    paper_id = str(uuid4())
    _add_source_pdf(paper_id, title="Manuscript", text=[text])
    save_references(
        paper_id,
        StoredReferenceList(
            metadata_version=2,
            paper_id=paper_id,
            source_file=f"{paper_id}.pdf",
            references=[
                StoredReference(
                    raw_text="[7] Smith. Retrieval with citations.",
                    number=number,
                    title="Retrieval with citations",
                    authors=["Smith, Jane"],
                    year=2024,
                )
            ],
        ),
    )
    return paper_id


def test_numeric_uses_reference_number_not_list_position(client):
    mid = manuscript()
    _add_source_pdf("source", title="Retrieval with citations")
    assert look_up_citation("[7]", exclude_paper_id=mid).source.record.paper_id == "source"
    missing = look_up_citation("[1]", exclude_paper_id=mid)
    assert missing.outcome == ComparisonStatus.REFERENCE_NOT_FOUND


def test_numeric_does_not_use_unrelated_bibliographies(client):
    mid = manuscript()
    _add_source_pdf("source", title="Retrieval with citations")
    _add_bibliography([_entry("7", title="Wrong paper")], "bib-a")
    _add_bibliography([_entry("7", title="Another wrong paper")], "bib-b")
    result = look_up_citation("[7]", exclude_paper_id=mid, bib_paper_id="bib-a")
    assert result.source.record.paper_id == "source"
    assert result.cited_source.database == "Manuscript reference list"


def test_explicit_bibliography_selects_correct_context(client):
    _add_source_pdf("source", title="Retrieval with citations")
    _add_bibliography([_entry("key", title="Wrong paper")], "bib-a")
    _add_bibliography([_entry("key", title="Retrieval with citations")], "bib-b")
    assert look_up_citation("key").outcome == ComparisonStatus.NO_BIBLIOGRAPHY
    assert look_up_citation("key", bib_paper_id="bib-b").source.record.paper_id == "source"
    assert not look_up_citation("key", bib_paper_id="missing").resolved


@pytest.mark.parametrize("marker", ["[7,8]", "[7-9]", "[7;8]"])
def test_multi_reference_requires_selection(client, marker):
    result = look_up_citation(marker, exclude_paper_id=manuscript())
    assert result.outcome == ComparisonStatus.REFERENCE_AMBIGUOUS
    assert result.source is None


def test_duplicate_source_titles_do_not_pick_arbitrary_pdf(client):
    mid = manuscript()
    _add_source_pdf("a", title="Retrieval with citations")
    _add_source_pdf("b", title="Retrieval with citations")
    assert not look_up_citation("[7]", exclude_paper_id=mid).resolved


def test_claims_and_verify_use_same_source_and_real_passages(client, monkeypatch):
    mid = manuscript()
    _add_source_pdf("source", title="Retrieval with citations")
    llm, retriever = FakeLLM(), FakeRetriever()
    monkeypatch.setenv("OPENAI_API_KEY", "test-not-real")
    get_settings.cache_clear()
    monkeypatch.setattr(engine_adapter, "_get_llm_client", lambda: llm)
    monkeypatch.setattr(citation_comparison_service, "_new_retriever", lambda: retriever)
    claims = client.get(f"/api/papers/{mid}/claims")
    assert claims.status_code == 200
    claim = claims.json()["claims"][0]
    response = client.post(
        "/api/verify/citation",
        json={
            "claim": claim["text"],
            "citation_marker": claim["citation_marker"],
            "manuscript_id": mid,
            "claim_id": claim["claim_id"],
        },
    )
    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "COMPARED"
    assert result["source_paper_id"] == claim["cited_source"]["source_paper_id"] == "source"
    assert result["claim_id"] == claim["claim_id"]
    assert result["evidence"][0]["page"] == 1
    assert retriever.passages and llm.calls


def test_claims_explicit_bibliography_query(client):
    mid = manuscript(text=r"A retrieval method improves checking \cite{key}.")
    _add_source_pdf("source", title="Retrieval with citations")
    _add_bibliography([_entry("key", title="Wrong paper")], "bib-a")
    _add_bibliography([_entry("key", title="Retrieval with citations")], "bib-b")
    response = client.get(f"/api/papers/{mid}/claims", params={"bib_paper_id": "bib-b"})
    assert response.status_code == 200
    assert response.json()["claims"][0]["cited_source"]["source_paper_id"] == "source"


def test_claims_reuse_reference_and_source_context_once_per_request(client, monkeypatch):
    mid = manuscript(
        text=(
            "A retrieval method improves citation checking [7]. "
            "A second experiment evaluates source linking [8]."
        )
    )
    save_references(
        mid,
        StoredReferenceList(
            metadata_version=2,
            paper_id=mid,
            source_file=f"{mid}.pdf",
            references=[
                StoredReference(
                    raw_text="[7] Smith. Retrieval with citations.",
                    number=7,
                    title="Retrieval with citations",
                    authors=["Smith, Jane"],
                    year=2024,
                ),
                StoredReference(
                    raw_text="[8] Jones. Source linking.",
                    number=8,
                    title="Source linking",
                    authors=["Jones, Alex"],
                    year=2023,
                ),
            ],
        ),
    )
    _add_source_pdf("source-7", title="Retrieval with citations")
    _add_source_pdf("source-8", title="Source linking")

    calls = {"papers": 0, "references": 0, "catalog": 0}
    original_list_papers = source_locator.list_papers
    original_load_references = source_locator.load_audit_references
    original_load_catalog = source_locator._load_source_catalog

    def counted_list_papers():
        calls["papers"] += 1
        return original_list_papers()

    def counted_load_references(request):
        calls["references"] += 1
        return original_load_references(request)

    def counted_load_catalog(records, *, exclude_paper_id):
        calls["catalog"] += 1
        return original_load_catalog(records, exclude_paper_id=exclude_paper_id)

    monkeypatch.setattr(source_locator, "list_papers", counted_list_papers)
    monkeypatch.setattr(source_locator, "load_audit_references", counted_load_references)
    monkeypatch.setattr(source_locator, "_load_source_catalog", counted_load_catalog)

    response = client.get(f"/api/papers/{mid}/claims")

    assert response.status_code == 200
    assert [claim["citation_marker"] for claim in response.json()["claims"]] == ["[7]", "[8]"]
    assert calls == {"papers": 1, "references": 1, "catalog": 1}


def test_missing_reference_input_is_not_a_verdict(client, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-not-real")
    get_settings.cache_clear()
    response = client.post(
        "/api/verify/citation",
        json={
            "claim": "A retrieval method improves checking [1].",
            "citation_marker": "[1]",
            "manuscript_id": str(uuid4()),
        },
    )
    assert response.status_code == 200
    assert response.json()["status"] == "SOURCE_NOT_AVAILABLE"
    assert response.json()["judgement"] is None


def test_author_year_uses_manuscript_references_without_bib(client):
    mid = manuscript(text="A retrieval method improves citation checking (Smith, 2024).")
    _add_source_pdf("source", title="Retrieval with citations")
    result = look_up_citation("(Smith, 2024)", exclude_paper_id=mid)
    assert result.source.record.paper_id == "source"
    assert result.cited_source.database == "Manuscript reference list"


def test_reference_numbers_are_scoped_to_the_selected_manuscript(client):
    first = manuscript()
    second = manuscript(number=9)
    _add_source_pdf("source", title="Retrieval with citations")
    assert look_up_citation("[7]", exclude_paper_id=first).resolved
    assert (
        look_up_citation("[7]", exclude_paper_id=second).outcome
        == ComparisonStatus.REFERENCE_NOT_FOUND
    )


def test_conflicting_doi_cannot_match_by_title(client):
    _add_bibliography([_entry("key", title="Retrieval with citations", doi="10.1/right")])
    _add_source_pdf("wrong", title="Retrieval with citations", doi="10.1/wrong")
    assert not look_up_citation("key").resolved


def test_duplicate_reference_numbers_are_ambiguous(client):
    mid = manuscript()
    save_references(
        mid,
        StoredReferenceList(
            metadata_version=2,
            paper_id=mid,
            source_file=f"{mid}.pdf",
            references=[
                StoredReference(raw_text="duplicate", number=7, title=title)
                for title in ("First", "Second")
            ],
        ),
    )
    assert (
        look_up_citation("[7]", exclude_paper_id=mid).outcome
        == ComparisonStatus.REFERENCE_AMBIGUOUS
    )


def test_corrupt_reference_artifact_is_not_silently_replaced(client):
    from backend.src.storage.reference_store import reference_path

    mid = manuscript()
    path = reference_path(mid)
    path.write_text("not-json", encoding="utf-8")
    result = look_up_citation("[7]", exclude_paper_id=mid)
    assert not result.resolved
    assert "REFERENCE_ARTIFACT_ERROR" in result.message
    assert path.read_text(encoding="utf-8") == "not-json"
