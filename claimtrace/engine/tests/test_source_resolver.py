"""Tests for source_resolver.py."""

from unittest.mock import Mock

from engine.retriever import RetrievalResult
from engine.source_resolver import ResolvedSource, SourcePaper, SourceResolver


def _locate(key: str) -> SourcePaper | None:
    if key == "missing":
        return None
    return SourcePaper(source_id="paper-1", title="Test Paper", metadata={"year": 2024})


def _parse(source: SourcePaper) -> list[str]:
    if source.source_id == "empty":
        return []
    return ["passage one", "passage two", "passage three"]


def test_resolve_returns_unresolved_when_locate_misses():
    resolver = SourceResolver(locate=_locate, parse=_parse)
    result = resolver.resolve("a claim", "missing")
    assert result.resolved is False
    assert result.citation_key == "missing"
    assert "missing" in result.reason
    assert result.passages == []
    assert result.retrieval == []


def test_resolve_retrieves_evidence_passages():
    retriever = Mock()
    fake_results = [
        RetrievalResult(passage="passage one", score=0.9, rank=1, passage_index=0),
        RetrievalResult(passage="passage two", score=0.8, rank=2, passage_index=1),
    ]
    retriever.retrieve.return_value = fake_results

    resolver = SourceResolver(locate=_locate, parse=_parse, retriever=retriever)
    result = resolver.resolve("a claim about passages", "cite1", k=2)

    assert result.resolved is True
    assert result.source_id == "paper-1"
    assert result.title == "Test Paper"
    assert result.passages == ["passage one", "passage two", "passage three"]
    assert result.retrieval == fake_results

    retriever.build_index.assert_called_once_with(
        ["passage one", "passage two", "passage three"]
    )
    retriever.retrieve.assert_called_once_with("a claim about passages", k=2)


def test_resolve_handles_empty_parse():
    def locate_empty(key: str) -> SourcePaper | None:
        return SourcePaper(source_id="empty", title=None)

    resolver = SourceResolver(locate=locate_empty, parse=_parse)
    result = resolver.resolve("a claim", "cite-empty")

    assert result.resolved is True
    assert result.source_id == "empty"
    assert result.passages == []
    assert result.retrieval == []
    assert "no passages" in result.reason.lower()


def test_resolver_defaults_to_real_retriever_when_omitted():
    resolver = SourceResolver(locate=_locate, parse=_parse)
    assert resolver._retriever is not None
