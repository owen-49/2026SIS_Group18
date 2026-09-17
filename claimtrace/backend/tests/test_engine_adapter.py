"""Regression coverage for integrating main's LLM Verify with PR #18."""

from types import SimpleNamespace

from backend.src.config import Settings
from backend.src.models import ParsedDocument, ParsedParagraph, VerdictEnum
from backend.src.services import engine_adapter


def test_llm_verdict_and_rationale_are_not_overwritten_by_lexical_match(monkeypatch):
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
            content='{"label": "CONTRADICT", "rationale": "The source reports no improvement."}'
        ))])

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    monkeypatch.setattr(engine_adapter, "_get_llm_client", lambda: client)
    monkeypatch.setattr(engine_adapter, "get_settings", lambda: Settings(llm_provider="deepseek"))
    source = "Treatment improves outcomes is a claim this trial did not support."
    document = ParsedDocument(
        paper_id="source", pages=1,
        paragraphs=[ParsedParagraph(text=source, page_start=1, page_end=1)],
    )

    result = engine_adapter.verify_claim("Treatment improves outcomes", document)

    assert result.verdict == VerdictEnum.CONTRADICT
    assert result.rationale == "The source reports no improvement."
    assert calls[0]["model"] == "deepseek-chat"
    assert source in str(calls[0]["messages"])


def test_no_llm_retains_local_baseline(monkeypatch):
    monkeypatch.setattr(engine_adapter, "_get_llm_client", lambda: None)
    document = ParsedDocument(
        paper_id="source", pages=1,
        paragraphs=[ParsedParagraph(text="Treatment improves outcomes", page_start=1, page_end=1)],
    )
    result = engine_adapter.verify_claim("Treatment improves outcomes", document)
    assert result.verdict == VerdictEnum.SUPPORT
    assert result.rationale.startswith("Local evidence analysis:")


# ── /api/verify degrades, but never fabricates ───────────────────
#
# The endpoint's response shape has no way to say "not judged" without a
# frontend change, so an Engine failure still lands on the documented lexical
# fallback. What changed is that the fallback is now reached by an explicit
# status branch instead of by an AttributeError on a None verdict — and that
# the Engine no longer hands this adapter a verdict it never reached.


def _client(reply, calls=None):
    def create(**kwargs):
        if calls is not None:
            calls.append(kwargs)
        if isinstance(reply, Exception):
            raise reply
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=reply))]
        )

    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))


def _document(text: str) -> ParsedDocument:
    return ParsedDocument(
        paper_id="source",
        pages=1,
        paragraphs=[ParsedParagraph(text=text, page_start=1, page_end=1)],
    )


def test_invalid_label_falls_back_to_the_local_baseline(monkeypatch):
    client = _client('{"label": "SUPPORTS", "rationale": "..."}')
    monkeypatch.setattr(engine_adapter, "_get_llm_client", lambda: client)

    result = engine_adapter.verify_claim(
        "Treatment improves outcomes", _document("Treatment improves outcomes")
    )

    assert result.verdict == VerdictEnum.SUPPORT
    assert result.confidence == 0.2
    assert result.rationale.startswith("LLM verification failed")


def test_model_error_falls_back_to_the_local_baseline(monkeypatch):
    client = _client(RuntimeError("upstream 502"))
    monkeypatch.setattr(engine_adapter, "_get_llm_client", lambda: client)

    result = engine_adapter.verify_claim(
        "Treatment improves outcomes", _document("Treatment improves outcomes")
    )

    assert result.verdict == VerdictEnum.SUPPORT
    assert result.confidence == 0.2
    assert result.rationale.startswith("LLM verification failed")


def test_unjudged_status_never_yields_a_fabricated_support(monkeypatch):
    """A bad label over unrelated text must not become a SUPPORT verdict."""
    client = _client('{"label": "NOPE", "rationale": "..."}')
    monkeypatch.setattr(engine_adapter, "_get_llm_client", lambda: client)

    result = engine_adapter.verify_claim(
        "Quantum entanglement mediates photosynthesis",
        _document("We present a table of contents and an acknowledgements section."),
    )

    assert result.verdict == VerdictEnum.NOT_FOUND
    assert result.rationale.startswith("LLM verification failed")


def test_blank_source_never_reaches_the_model(monkeypatch):
    """An empty passage is not evidence, so the model is not consulted.

    Previously the empty string was sent as the source text and the reply was
    reported as a judgement about it.
    """
    calls: list[dict] = []
    client = _client('{"label": "SUPPORT", "rationale": "sure"}', calls)
    monkeypatch.setattr(engine_adapter, "_get_llm_client", lambda: client)

    result = engine_adapter.verify_claim("Treatment improves outcomes", _document(""))

    assert calls == [], "the model must not be asked to judge empty source text"
    assert result.verdict == VerdictEnum.NOT_FOUND
    assert result.rationale.startswith("LLM verification failed")
