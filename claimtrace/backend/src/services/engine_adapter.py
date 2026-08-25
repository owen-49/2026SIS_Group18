"""Stable adapter for Engine integration using deterministic mock logic."""

import re

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


def verify_claim(claim: str, document: ParsedDocument) -> VerifyResponse:
    """Compare a claim with mock Parser output using deterministic overlap."""
    clean_claim = claim.strip()
    if not clean_claim:
        raise EngineAdapterError("Claim text is required.")
    if not document.paragraphs:
        raise EngineAdapterError("The parsed document contains no paragraphs.")

    ranked = sorted(
        (
            (_similarity(clean_claim, paragraph.text), paragraph.text)
            for paragraph in document.paragraphs
        ),
        key=lambda item: item[0],
        reverse=True,
    )
    best_score = ranked[0][0]
    verdict = VerdictEnum.SUPPORT if best_score >= 0.2 else VerdictEnum.NOT_FOUND
    confidence = min(0.95, 0.55 + best_score) if verdict == VerdictEnum.SUPPORT else 0.2

    matches = [
        MatchResult(
            passage_text=passage,
            similarity=round(score, 4),
            entailment_label=verdict,
            confidence=round(confidence, 4),
        )
        for score, passage in ranked[:3]
    ]

    rationale = (
        "Mock Engine result: the highest-overlap parsed passage supports the claim."
        if verdict == VerdictEnum.SUPPORT
        else "Mock Engine result: no parsed passage has enough lexical overlap with the claim."
    )
    return VerifyResponse(
        claim=clean_claim,
        verdict=verdict,
        confidence=round(confidence, 4),
        rationale=rationale,
        matches=matches,
    )
