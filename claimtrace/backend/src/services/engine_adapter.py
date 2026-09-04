"""Adapter between the backend contract and the Engine's LLM verifier.

Retrieval uses deterministic lexical-overlap ranking (a fast stand-in for the
Engine's FAISS retriever). Entailment verification is delegated to the real
Engine Verifier backed by the configured LLM (DeepSeek / OpenAI / Gemini / ...).

When no LLM client is configured (no API key), it falls back to the old
deterministic mock verdict so CI and local dev without keys still work.
"""

import re
from functools import lru_cache

from engine.llm_client import build_llm_client
from engine.verifier import Verifier

from ..config import get_settings
from ..models import MatchResult, ParsedDocument, VerdictEnum, VerifyResponse


class EngineAdapterError(RuntimeError):
    """Raised when the Engine cannot compare a claim with parsed content."""


def _tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", text.lower())
        if len(token) > 2
    }


def _similarity(claim: str, passage: str) -> float:
    claim_tokens = _tokens(claim)
    passage_tokens = _tokens(passage)
    if not claim_tokens or not passage_tokens:
        return 0.0
    return len(claim_tokens & passage_tokens) / len(claim_tokens)


@lru_cache(maxsize=1)
def _get_llm_client():
    """Build (and cache) the LLM client from application settings."""
    settings = get_settings()
    provider = settings.llm_provider
    provider_configs = {
        "openai": {
            "api_key": settings.openai_api_key,
            "base_url": settings.openai_base_url,
        },
        "deepseek": {
            "api_key": settings.deepseek_api_key,
            "base_url": settings.deepseek_base_url,
        },
        "gemini": {
            "api_key": settings.gemini_api_key,
            "base_url": None,
        },
        "anthropic": {
            "api_key": settings.anthropic_api_key,
            "base_url": None,
        },
        "ollama": {
            "api_key": "",
            "base_url": settings.ollama_base_url,
        },
    }
    config = provider_configs.get(provider, {})
    return build_llm_client(provider=provider, **config)


def verify_claim(claim: str, document: ParsedDocument) -> VerifyResponse:
    """Verify a claim against a parsed document.

    Ranks paragraphs by lexical overlap to pick the best-matching passage,
    then asks the Engine Verifier (backed by the configured LLM) for an
    entailment verdict. Falls back to a deterministic mock verdict when no
    LLM client is available.
    """
    clean_claim = claim.strip()
    if not clean_claim:
        raise EngineAdapterError("Claim text is required.")
    if not document.paragraphs:
        raise EngineAdapterError("The parsed document contains no paragraphs.")

    # ── 1. Retrieve: rank paragraphs by lexical overlap ─────
    ranked = sorted(
        (
            (_similarity(clean_claim, paragraph.text), paragraph.text)
            for paragraph in document.paragraphs
        ),
        key=lambda item: item[0],
        reverse=True,
    )
    best_score = ranked[0][0]
    best_passage = ranked[0][1]

    # ── 2. Verify: real LLM entailment, with mock fallback ──
    client = _get_llm_client()
    if client is not None:
        settings = get_settings()
        verifier = Verifier(model=settings.llm_model_name)
        try:
            result = verifier.verify(clean_claim, best_passage, client=client)
            verdict = VerdictEnum(result.verdict.value)
            confidence = result.confidence
            rationale = result.rationale
        except Exception as exc:  # LLM call failure → degrade to mock
            verdict = VerdictEnum.SUPPORT if best_score >= 0.2 else VerdictEnum.NOT_FOUND
            confidence = 0.2
            rationale = f"LLM verification failed ({exc}); mock fallback used."
    else:
        verdict = VerdictEnum.SUPPORT if best_score >= 0.2 else VerdictEnum.NOT_FOUND
        confidence = min(0.95, 0.55 + best_score) if verdict == VerdictEnum.SUPPORT else 0.2
        rationale = (
            "Mock Engine result: the highest-overlap parsed passage supports the claim."
            if verdict == VerdictEnum.SUPPORT
            else "Mock Engine result: no parsed passage has enough lexical overlap with the claim."
        )

    # ── 3. Build matches (top-3 passages) ───────────────────
    matches = [
        MatchResult(
            passage_text=passage,
            similarity=round(score, 4),
            entailment_label=verdict,
            confidence=round(confidence, 4),
        )
        for score, passage in ranked[:3]
    ]

    return VerifyResponse(
        claim=clean_claim,
        verdict=verdict,
        confidence=round(confidence, 4),
        rationale=rationale,
        matches=matches,
    )
