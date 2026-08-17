"""Tests for verifier.py — Pair 2-B."""

import pytest

from engine.retriever import RetrievalResult
from engine.verifier import Verdict, VerificationResult, Verifier


class TestVerifier:
    @pytest.fixture
    def verifier(self):
        return Verifier()

    def test_mock_mode_returns_not_found(self, verifier):
        """Without a real LLM client, verifier returns mock result."""
        result = verifier.verify(
            claim="The model achieves SOTA performance.",
            source_passage="We report results competitive with prior work.",
            client=None,  # mock mode
        )
        assert isinstance(result, VerificationResult)
        assert result.verdict == Verdict.NOT_FOUND
        assert "Mock" in result.rationale

    def test_prompt_is_built_correctly(self, verifier):
        prompt = verifier._build_prompt("Claim text", "Source text")
        assert "Claim text" in prompt
        assert "Source text" in prompt
        assert "SUPPORT" in prompt
        assert "PARTIAL" in prompt
        assert "CONTRADICT" in prompt
        assert "NOT_FOUND" in prompt

    def test_verify_with_retrieval_no_results(self, verifier):
        """Empty retrieval should return NOT_FOUND."""
        result = verifier.verify_with_retrieval("any claim", [])
        assert result.verdict == Verdict.NOT_FOUND

    def test_verify_with_retrieval_mock(self, verifier):
        """With retrieval results but no client, should still work."""
        results = [
            RetrievalResult(
                passage="We observe improvements with scale.",
                score=0.85,
                rank=1,
                passage_index=0,
            )
        ]
        result = verifier.verify_with_retrieval(
            "Larger models perform better.", results, client=None
        )
        assert result.verdict == Verdict.NOT_FOUND  # mock mode
        assert result.best_match is not None
        assert result.best_match.score == 0.85
