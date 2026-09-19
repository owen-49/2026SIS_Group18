"""Adapter between the backend contract and the Engine's LLM verifier.

Retrieval uses deterministic lexical-overlap ranking (a fast stand-in for the
Engine's FAISS retriever). Entailment verification is delegated to the real
Engine Verifier backed by the configured LLM (DeepSeek / OpenAI / Gemini / ...).

When no LLM client is configured (no API key), it falls back to the old
deterministic lexical verdict so CI and local dev without keys still work.

A configured Engine that completes *without* a verdict is a different case, and
is not a fallback: it raises :class:`ClaimNotJudgedError`, which the route
reports as a failure. Five of the Engine's statuses mean "the claim was not
judged" — never "the claim is unsupported" — and ``NOT_FOUND`` is itself a
verdict (the source exists and does not state the claim), so inventing one here
would report a finding the Engine never made.
"""

import re
from functools import lru_cache

from engine.llm_client import build_llm_client
from engine.verifier import VerificationStatus, Verifier

from ..config import get_settings
from ..models import MatchResult, ParsedDocument, VerdictEnum, VerifyResponse


class EngineAdapterError(RuntimeError):
    """Raised when the Engine cannot compare a claim with parsed content."""


class ClaimNotJudgedError(RuntimeError):
    """Raised when the Engine completed without reaching a verdict.

    Deliberately **not** an :class:`EngineAdapterError`. That class means "this
    adapter failed", and ``verification_service`` normalises it into a generic
    500 — which would destroy the two things this exception carries: the
    Engine's own status and its rationale. A claim the Engine declined to judge
    is a reportable outcome, not an internal fault.

    Attributes:
        code: The Engine's ``VerificationStatus`` value. Each one points at a
            different thing to fix, so the reason is not collapsed into a
            single opaque failure.
        message: The Engine's rationale, verbatim.
    """

    def __init__(self, *, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


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


@lru_cache(maxsize=1)
def _get_embedder():
    """Build (and cache) the sentence-transformers embedder.

    Constructing an ``Embedder`` loads the sentence-transformers model from
    disk — measured at ~4.4s here — while indexing a few hundred passages costs
    ~0.4s. The model is stateless and thread-safe once loaded, so it is cached
    process-wide; the ``Retriever`` built on top of it is *not* (it holds the
    per-document index) and must be constructed per request.

    The import is deferred: ``sentence_transformers`` pulls in torch, and this
    module is imported at application start-up for the unrelated ``/api/verify``
    route.
    """
    from engine.embedder import Embedder

    return Embedder()


def verify_claim(claim: str, document: ParsedDocument) -> VerifyResponse:
    """Verify a claim against a parsed document.

    Ranks paragraphs by lexical overlap to pick the best-matching passage,
    then asks the Engine Verifier (backed by the configured LLM) for an
    entailment verdict. Falls back to a deterministic lexical verdict when no
    LLM client is available.

    Raises:
        EngineAdapterError: The claim or document is unusable, or the Engine
            raised something it does not model as a status.
        ClaimNotJudgedError: A configured Engine completed without a verdict.
            Never a fallback: the caller must report a failure rather than a
            finding.
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

    # ── 2. Verify: real LLM entailment, or the documented baseline ──
    client = _get_llm_client()
    if client is not None:
        settings = get_settings()
        verifier = Verifier(model=settings.llm_model_name)
        try:
            result = verifier.verify(clean_claim, best_passage, client=client)
        except Exception as exc:
            # Safety net: unexpected faults only. The Engine reports its own
            # failures as statuses rather than raising, so anything arriving
            # here is a provider SDK fault mid-flight or a bug in this module.
            raise EngineAdapterError(f"The Engine call failed: {exc}") from exc

        if result.status is not VerificationStatus.JUDGED:
            # The Engine declined to judge — it had no usable evidence, the call
            # failed, or the reply was unusable. Every one of those statuses
            # means "the claim was not judged", never "the claim is
            # unsupported", and NOT_FOUND is itself a verdict (the source exists
            # and does not state the claim). This endpoint's response contract
            # has no slot to say "not judged", so the outcome is reported as a
            # failure rather than dressed up as a finding the Engine never made.
            # The status travels as the error code because each one points at a
            # different thing to fix.
            #
            # Raised outside the ``try`` above on purpose: inside it, the safety
            # net would catch it and re-wrap it as an adapter fault.
            raise ClaimNotJudgedError(code=result.status.value, message=result.rationale)

        # Outside the safety net too. The four-member Verdict/VerdictEnum
        # contract is pinned by tests in both packages, so a mismatch is a code
        # defect that must fail loudly rather than be absorbed as a fallback.
        verdict = VerdictEnum(result.verdict.value)
        confidence = result.confidence
        rationale = result.rationale
    else:
        verdict = VerdictEnum.SUPPORT if best_score >= 0.2 else VerdictEnum.NOT_FOUND
        confidence = min(0.95, 0.55 + best_score) if verdict == VerdictEnum.SUPPORT else 0.2
        rationale = (
            "Local evidence analysis: the highest-overlap parsed passage supports the claim."
            if verdict == VerdictEnum.SUPPORT
            else "Local evidence analysis: no parsed passage has enough lexical overlap "
            "with the claim."
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
