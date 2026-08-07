"""Tests for retriever.py — Pair 2-A."""

import pytest

from engine.src.embedder import Embedder
from engine.src.retriever import RetrievalResult, Retriever


class TestRetriever:
    @pytest.fixture
    def retriever(self):
        """A retriever pre-loaded with sample passages."""
        ret = Retriever(Embedder())
        passages = [
            "Model performance improves discontinuously with scale, "
            "consistent with empirical signatures of emergence.",
            "We evaluate on six benchmark datasets spanning natural "
            "language understanding and generation tasks.",
            "All experiments were run on 8× A100 GPUs with a batch "
            "size of 128 and the AdamW optimizer.",
            "Training converges after approximately 50,000 steps, "
            "with diminishing returns beyond this point.",
        ]
        ret.build_index(passages)
        return ret

    def test_build_index(self, retriever):
        assert retriever.index is not None
        assert len(retriever.passages) == 4

    def test_retrieve_returns_results(self, retriever):
        results = retriever.retrieve(
            "The model shows emergent abilities when scaled up", k=2
        )
        assert len(results) == 2
        assert isinstance(results[0], RetrievalResult)
        assert results[0].score > 0

    def test_retrieve_top_result_is_most_relevant(self, retriever):
        results = retriever.retrieve(
            "The model exhibits emergent capabilities at scale", k=1
        )
        assert len(results) == 1
        # The first passage should match because it talks about emergence
        assert "emergence" in results[0].passage.lower()

    def test_sentence_level_retrieval(self, retriever):
        """Two-stage retrieval should return sentence-level results."""
        results = retriever.retrieve_with_sentences(
            "emergent abilities at scale", k_paragraphs=2, k_sentences=2
        )
        assert len(results) >= 1
        # Sentence-level results should be shorter than full paragraphs
        for r in results:
            assert len(r.passage.split()) < 50  # reasonable sentence length


class TestRetrieverEmpty:
    def test_empty_index(self):
        ret = Retriever()
        results = ret.retrieve("any claim")
        assert results == []

    def test_sentence_retrieval_empty(self):
        ret = Retriever()
        results = ret.retrieve_with_sentences("any claim")
        assert results == []
