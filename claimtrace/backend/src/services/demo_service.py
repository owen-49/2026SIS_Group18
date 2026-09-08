"""Deterministic demo responses used until the verification engine is connected."""

from ..models import (
    MatchResult,
    VerdictEnum,
    VerifyResponse,
)


def build_demo_verification(claim: str, source_paper_id: str) -> VerifyResponse:
    """Return a frontend-compatible verification result without calling the engine."""
    source_passages = {
        "paper-attention": (
            "We propose a new simple network architecture, the Transformer, based solely "
            "on attention mechanisms, dispensing with recurrence and convolutions entirely."
        ),
        "paper-bert": (
            "BERT is designed to pre-train deep bidirectional representations from "
            "unlabelled text by jointly conditioning on both left and right context."
        ),
        "paper-gpt3": (
            "Scaling up language models greatly improves task-agnostic, few-shot performance."
        ),
        "paper-rag": (
            "Retrieval-augmented generation combines parametric and non-parametric memory."
        ),
    }
    passage = source_passages.get(
        source_paper_id,
        "Demo evidence passage for the selected source paper.",
    )

    return VerifyResponse(
        claim=claim,
        verdict=VerdictEnum.SUPPORT,
        confidence=0.94,
        rationale="Demo result: the selected source passage supports the claim.",
        matches=[
            MatchResult(
                passage_text=passage,
                similarity=0.91,
                entailment_label=VerdictEnum.SUPPORT,
                confidence=0.94,
            )
        ],
    )
