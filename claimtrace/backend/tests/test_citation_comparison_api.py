"""Contract tests for POST /api/verify/citation.

Fully offline: the retriever and the LLM client are replaced with fakes at the
service's seams. ``SimpleNamespace`` stands in for ``RetrievalResult`` so that
importing it never pulls in torch.
"""

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from backend.src.config import get_settings
from backend.src.models import (
    BibEntryRecord,
    PaperRecord,
    ParsedBibDocument,
    ParsedDocument,
    ParsedParagraph,
    ParseStatus,
)
from backend.src.services import citation_comparison_service, engine_adapter
from backend.src.storage.bib_document_store import save_bib_document
from backend.src.storage.paper_store import create_paper
from backend.src.storage.parsed_document_store import save_parsed_document

MARKER = "\\cite{smith2024}"
CLAIM = "Self-attention lets the model relate distant positions without recurrence."

PASSAGES = [
    "Self-attention enables the model to relate information from different positions "
    "without recurrence.",
    "The experiment evaluates citation verification quality using source passages.",
    "Unrelated closing remarks about future work.",
]

SUPPORT_REPLY = '{"label": "SUPPORT", "rationale": "The passage states exactly this."}'


# ── Fakes --------------------------------------------------------


class FakeRetriever:
    """Stands in for ``engine.Retriever``; records what it was asked to index."""

    def __init__(self, scores=None, results=None):
        self.passages: list[str] = []
        self.queries: list[str] = []
        self.scores = scores
        self.results = results

    def build_index(self, passages):
        self.passages = list(passages)

    def retrieve(self, claim, k=5):
        self.queries.append(claim)
        if self.results is not None:
            return self.results
        results = []
        for rank, index in enumerate(range(min(k, len(self.passages)))):
            score = self.scores[rank] if self.scores else 0.9 - 0.1 * rank
            results.append(
                SimpleNamespace(
                    passage=self.passages[index],
                    score=score,
                    rank=rank + 1,
                    passage_index=index,
                )
            )
        return results


class FakeCompletions:
    def __init__(self, owner):
        self._owner = owner

    def create(self, **kwargs):
        self._owner.calls.append(kwargs)
        if isinstance(self._owner.reply, Exception):
            raise self._owner.reply
        message = SimpleNamespace(content=self._owner.reply)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


class FakeLLM:
    """Minimal OpenAI-compatible client: ``.chat.completions.create(...)``."""

    def __init__(self, reply=SUPPORT_REPLY):
        self.reply = reply
        self.calls: list[dict] = []
        self.chat = SimpleNamespace(completions=FakeCompletions(self))

    @property
    def prompt(self) -> str:
        assert self.calls, "the LLM was never called"
        return self.calls[-1]["messages"][0]["content"]


# ── Fixtures -----------------------------------------------------


@pytest.fixture()
def seeded(storage_paths):
    """One .bib whose single reference matches one parsed source PDF."""
    del storage_paths
    now = datetime.now(UTC)

    source = ParsedDocument(
        paper_id="pdf-1",
        title="Retrieval with citations",
        authors=["Smith, Jane"],
        year=2024,
        doi="10.1234/example",
        pages=1,
        paragraphs=[
            ParsedParagraph(text=chunk, page_start=1, page_end=1) for chunk in PASSAGES
        ],
    )
    create_paper(
        PaperRecord(
            paper_id="pdf-1",
            original_filename="source.pdf",
            stored_filename="source.pdf",
            file_path="/uploads/source.pdf",
            parsed_result_path=str(save_parsed_document(source)),
            file_type="pdf",
            file_size=10,
            status=ParseStatus.COMPLETED,
            pages=1,
            created_at=now,
            updated_at=now,
        )
    )

    bib = ParsedBibDocument(
        paper_id="bib-1",
        entries=[
            BibEntryRecord(
                key="smith2024",
                title="Retrieval with citations",
                authors=["Smith, Jane"],
                year=2024,
                doi="10.1234/example",
            )
        ],
    )
    create_paper(
        PaperRecord(
            paper_id="bib-1",
            original_filename="references.bib",
            stored_filename="references.bib",
            file_path="/uploads/references.bib",
            parsed_result_path=str(save_bib_document(bib)),
            file_type="bib",
            file_size=10,
            status=ParseStatus.COMPLETED,
            pages=1,
            created_at=now,
            updated_at=now,
        )
    )


@pytest.fixture()
def llm_configured(monkeypatch):
    """Make ``settings.is_llm_configured`` true without any real key."""
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-real")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture()
def wired(monkeypatch, llm_configured):
    """Wire a fake retriever and a fake LLM into the comparison service."""
    retriever = FakeRetriever()
    llm = FakeLLM()
    built: list[FakeRetriever] = []

    def build_retriever():
        built.append(retriever)
        return retriever

    monkeypatch.setattr(citation_comparison_service, "_new_retriever", build_retriever)
    monkeypatch.setattr(engine_adapter, "_get_llm_client", lambda: llm)
    return SimpleNamespace(retriever=retriever, llm=llm, built=built)


def post(client, **overrides):
    payload = {"claim": CLAIM, "citation_marker": MARKER}
    payload.update(overrides)
    return client.post("/api/verify/citation", json=payload)


# ── Happy path ---------------------------------------------------


def test_compared_claim_returns_a_real_verdict(client, seeded, wired):
    response = post(client)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "COMPARED"
    assert body["citation_key"] == "smith2024"
    assert body["source_paper_id"] == "pdf-1"
    assert body["judgement"]["verdict"] == "SUPPORT"
    assert body["judgement"]["rationale"] == "The passage states exactly this."
    assert body["judgement"]["confidence"] > 0
    assert body["cited_source"]["title"] == "Retrieval with citations"


def test_evidence_carries_page_and_display_location(client, seeded, wired):
    body = post(client).json()
    evidence = body["evidence"]

    assert evidence, "expected retrieved evidence"
    assert evidence[0]["passage_text"] == PASSAGES[0]
    # The 1:1 passage/paragraph invariant is what makes this page number right.
    assert evidence[0]["page"] == 1
    assert evidence[0]["rank"] == 1
    assert evidence[0]["location"]["page"] == 1
    assert body["source_document"]["matched_location"] == evidence[0]["location"]


def test_retriever_indexes_the_source_paper_passages(client, seeded, wired):
    post(client)

    assert wired.retriever.passages == PASSAGES
    assert wired.retriever.queries == [CLAIM]


def test_claim_and_source_text_reach_the_prompt(client, seeded, wired):
    post(client)
    prompt = wired.llm.prompt

    assert CLAIM in prompt
    assert PASSAGES[0] in prompt


def test_verdict_is_not_overwritten_by_any_local_baseline(client, seeded, wired):
    """A CONTRADICT verdict must survive; nothing local may downgrade it."""
    wired.llm.reply = '{"label": "CONTRADICT", "rationale": "The source says the opposite."}'

    body = post(client).json()

    assert body["status"] == "COMPARED"
    assert body["judgement"]["verdict"] == "CONTRADICT"


# ── LLM failures -------------------------------------------------


def test_missing_api_key_is_503_and_never_builds_a_retriever(client, seeded, monkeypatch):
    """A deployment fault must fail loudly, not fabricate a NOT_FOUND verdict."""
    built: list[object] = []
    monkeypatch.setattr(
        citation_comparison_service, "_new_retriever", lambda: built.append(1)
    )

    response = post(client)

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "LLM_NOT_CONFIGURED"
    # Fail fast: no embedding work is done before the configuration is checked.
    assert built == []


def test_llm_error_is_reported_as_llm_failed_but_keeps_the_evidence(client, seeded, wired):
    wired.llm.reply = RuntimeError("upstream 502")

    response = post(client)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "LLM_FAILED"
    assert body["judgement"] is None
    # The source and its evidence were genuinely obtained; a 5xx would discard them.
    assert len(body["evidence"]) == len(PASSAGES)
    assert body["cited_source"]["title"] == "Retrieval with citations"


def test_out_of_enum_label_is_llm_failed_not_a_500(client, seeded, wired):
    """The Engine builds Verdict(label) outside its try/except (verifier.py:132)."""
    wired.llm.reply = '{"label": "SUPPORTS", "rationale": "..."}'

    response = post(client)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "LLM_FAILED"
    assert body["judgement"] is None
    assert "SUPPORTS" in body["message"]


def test_unparseable_json_reply_becomes_a_not_found_verdict(client, seeded, wired):
    """Engine trap #3, pinned so a change of behaviour is deliberate.

    The Engine's JSONDecodeError handler substitutes the label ``NOT_FOUND`` and
    only mentions the parse failure in the rationale, so a malformed model reply
    is reported as a real verdict rather than a failure. The rationale is
    surfaced to the user verbatim, which is why this is tolerated rather than
    patched over — remapping it would mean string-matching the Engine's own
    error text. Flagged for the Engine owners in the handoff document.
    """
    wired.llm.reply = "not json at all"

    body = post(client).json()

    assert body["status"] == "COMPARED"
    assert body["judgement"]["verdict"] == "NOT_FOUND"
    assert body["judgement"]["rationale"].startswith("Failed to parse LLM response")


def test_empty_retrieval_is_never_sent_to_the_llm(client, seeded, monkeypatch, llm_configured):
    """Verifier.verify_with_retrieval fabricates NOT_FOUND on empty input."""
    llm = FakeLLM()
    monkeypatch.setattr(engine_adapter, "_get_llm_client", lambda: llm)
    monkeypatch.setattr(
        citation_comparison_service,
        "_new_retriever",
        lambda: FakeRetriever(results=[]),
    )

    body = post(client).json()

    assert body["status"] == "SOURCE_EMPTY"
    assert body["judgement"] is None
    assert llm.calls == [], "the LLM must not be consulted without evidence"


# ── Score clamping -----------------------------------------------


def test_negative_cosine_similarity_is_clamped_not_a_500(
    client, seeded, monkeypatch, llm_configured
):
    """IndexFlatIP over unrelated text returns negative scores; ge=0.0 would 500."""
    monkeypatch.setattr(engine_adapter, "_get_llm_client", lambda: FakeLLM())
    monkeypatch.setattr(
        citation_comparison_service,
        "_new_retriever",
        lambda: FakeRetriever(scores=[-0.105, -0.4, 1.7]),
    )

    response = post(client)

    assert response.status_code == 200
    body = response.json()
    assert [item["similarity"] for item in body["evidence"]] == [0.0, 0.0, 1.0]


# ── Resolution failures are data, not errors ---------------------


def test_unknown_reference_is_reported_without_a_judgement(client, seeded, wired):
    response = post(client, citation_marker="\\cite{nobody1999}")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "REFERENCE_NOT_FOUND"
    assert body["judgement"] is None
    assert body["evidence"] == []
    assert body["cited_source"] is None


def test_numeric_marker_is_unsupported_not_a_server_error(client, seeded, wired):
    body = post(client, citation_marker="[1]").json()

    assert body["status"] == "MARKER_UNSUPPORTED"
    assert body["judgement"] is None


def test_reference_without_a_local_pdf_reports_the_matched_metadata(client, seeded, wired):
    body = post(client, manuscript_id="pdf-1").json()

    assert body["status"] == "SOURCE_NOT_AVAILABLE"
    assert body["judgement"] is None
    # The bibliography entry was still found, so it is still reported.
    assert body["citation_key"] == "smith2024"


def test_empty_paragraphs_document_is_source_empty(client, seeded, wired):
    """Point the bibliography at a paper whose parse produced no paragraphs."""
    empty = ParsedDocument(
        paper_id="pdf-1", title="Retrieval with citations", pages=1, paragraphs=[]
    )
    save_parsed_document(empty)

    body = post(client).json()

    assert body["status"] == "SOURCE_EMPTY"
    assert body["judgement"] is None


# ── Request validation -------------------------------------------


def test_blank_claim_is_rejected(client, seeded, wired):
    assert post(client, claim="").status_code == 422
    assert post(client, claim="   ").status_code == 422


def test_blank_marker_is_rejected(client, seeded, wired):
    assert post(client, citation_marker="   ").status_code == 422


def test_unknown_fields_are_rejected(client, seeded, wired):
    assert post(client, unexpected="x").status_code == 422


def test_claim_id_is_echoed_for_batch_callers(client, seeded, wired):
    assert post(client, claim_id="claim-abc").json()["claim_id"] == "claim-abc"


def test_k_bounds_are_enforced(client, seeded, wired):
    assert post(client, k=0).status_code == 422
    assert post(client, k=11).status_code == 422


# ── The existing endpoint is untouched ---------------------------


def test_openapi_exposes_both_verify_routes(client):
    paths = client.get("/openapi.json").json()["paths"]

    assert "/api/verify" in paths
    assert "/api/verify/citation" in paths
