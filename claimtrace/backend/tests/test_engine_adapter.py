"""Regression coverage for integrating main's LLM Verify with PR #18."""

from types import SimpleNamespace

import pytest
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


# ── an unjudged claim is reported, never converted into a verdict ──
#
# Every non-JUDGED Engine status means "the claim was not judged" — never "the
# claim is unsupported" — and NOT_FOUND is itself a verdict (the source exists
# and does not state the claim). The endpoint's response shape has no way to say
# "not judged" without a frontend change, so the outcome leaves this adapter as
# a ClaimNotJudgedError and the route turns it into a 503 carrying the Engine's
# status and rationale. Returning a verdict here would report a finding the
# Engine never made.
#
# The no-client baseline above is a different thing: it is the endpoint's
# announced degraded mode, not a model call that failed.


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


def test_an_unusable_label_is_not_reported_as_a_verdict(monkeypatch):
    client = _client('{"label": "SUPPORTS", "rationale": "..."}')
    monkeypatch.setattr(engine_adapter, "_get_llm_client", lambda: client)

    with pytest.raises(engine_adapter.ClaimNotJudgedError) as raised:
        engine_adapter.verify_claim(
            "Treatment improves outcomes", _document("Treatment improves outcomes")
        )

    assert raised.value.code == "INVALID_LABEL"
    # The Engine's own diagnostic, naming the label it could not use, is what
    # the caller gets to see — not a paraphrase and not a verdict.
    assert "SUPPORTS" in raised.value.message


def test_a_model_error_is_not_reported_as_a_verdict(monkeypatch):
    client = _client(RuntimeError("upstream 502"))
    monkeypatch.setattr(engine_adapter, "_get_llm_client", lambda: client)

    with pytest.raises(engine_adapter.ClaimNotJudgedError) as raised:
        engine_adapter.verify_claim(
            "Treatment improves outcomes", _document("Treatment improves outcomes")
        )

    assert raised.value.code == "MODEL_ERROR"


def test_unjudged_status_never_yields_a_fabricated_support(monkeypatch):
    """A bad label over unrelated text must not become a NOT_FOUND verdict.

    The lexical overlap here is far below the threshold the old fallback used,
    so it would have reported the claim as absent from the source — a finding
    the Engine never made.
    """
    client = _client('{"label": "NOPE", "rationale": "..."}')
    monkeypatch.setattr(engine_adapter, "_get_llm_client", lambda: client)

    with pytest.raises(engine_adapter.ClaimNotJudgedError) as raised:
        engine_adapter.verify_claim(
            "Quantum entanglement mediates photosynthesis",
            _document("We present a table of contents and an acknowledgements section."),
        )

    assert raised.value.code == "INVALID_LABEL"


def test_blank_source_never_reaches_the_model(monkeypatch):
    """An empty passage is not evidence, so the model is not consulted.

    Previously the empty string was sent as the source text and the reply was
    reported as a judgement about it.
    """
    calls: list[dict] = []
    client = _client('{"label": "SUPPORT", "rationale": "sure"}', calls)
    monkeypatch.setattr(engine_adapter, "_get_llm_client", lambda: client)

    with pytest.raises(engine_adapter.ClaimNotJudgedError) as raised:
        engine_adapter.verify_claim("Treatment improves outcomes", _document(""))

    assert calls == [], "the model must not be asked to judge empty source text"
    assert raised.value.code == "NO_EVIDENCE"


@pytest.mark.parametrize(
    ("reply", "document_text", "expected_code"),
    [
        (RuntimeError("upstream 502"), "Treatment improves outcomes", "MODEL_ERROR"),
        ("not json at all", "Treatment improves outcomes", "INVALID_RESPONSE"),
        ("[1, 2, 3]", "Treatment improves outcomes", "INVALID_RESPONSE"),
        ('{"rationale": "no label here"}', "Treatment improves outcomes", "INVALID_LABEL"),
        ('{"label": "SUPPORTS"}', "Treatment improves outcomes", "INVALID_LABEL"),
        ('{"label": "SUPPORT", "rationale": "sure"}', "", "NO_EVIDENCE"),
    ],
)
def test_every_unjudged_engine_status_travels_as_its_own_code(
    monkeypatch, reply, document_text, expected_code
):
    """Each failure keeps its own code, so the reason is not collapsed.

    ``NO_CLIENT`` is absent because it is unreachable here: this adapter only
    consults the Engine when a client was built.
    """
    monkeypatch.setattr(engine_adapter, "_get_llm_client", lambda: _client(reply))

    with pytest.raises(engine_adapter.ClaimNotJudgedError) as raised:
        engine_adapter.verify_claim(
            "Treatment improves outcomes", _document(document_text)
        )

    assert raised.value.code == expected_code
