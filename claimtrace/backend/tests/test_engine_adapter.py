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
