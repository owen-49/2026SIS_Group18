"""Deterministic demo responses used until the verification engine is connected."""

from ..models import (
    AuditResponse,
    CitationAuditResult,
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


def build_demo_audit(
    manuscript_id: str,
    source_paper_ids: list[str],
) -> AuditResponse:
    """Return a consistent, non-empty audit result for frontend integration."""
    templates = [
        (
            "vaswani2017attention",
            "The Transformer removes recurrence in favour of attention mechanisms.",
            VerdictEnum.SUPPORT,
            0.94,
            "low",
        ),
        (
            "devlin2019bert",
            "BERT was trained exclusively with a next-sentence prediction objective.",
            VerdictEnum.CONTRADICT,
            0.89,
            "high",
        ),
        (
            "brown2020language",
            "Larger language models always improve few-shot performance.",
            VerdictEnum.PARTIAL,
            0.82,
            "medium",
        ),
        (
            "lewis2020retrieval",
            "RAG combines parametric and non-parametric memory.",
            VerdictEnum.SUPPORT,
            0.91,
            "low",
        ),
    ]

    results = [
        CitationAuditResult(
            citation_key=templates[index % len(templates)][0],
            claim=templates[index % len(templates)][1],
            verdict=templates[index % len(templates)][2],
            confidence=templates[index % len(templates)][3],
            risk_level=templates[index % len(templates)][4],
        )
        for index, _paper_id in enumerate(source_paper_ids)
    ]

    return AuditResponse(
        manuscript_id=manuscript_id,
        total_citations=len(results),
        supported=sum(item.verdict == VerdictEnum.SUPPORT for item in results),
        partial=sum(item.verdict == VerdictEnum.PARTIAL for item in results),
        contradicted=sum(item.verdict == VerdictEnum.CONTRADICT for item in results),
        not_found=sum(item.verdict == VerdictEnum.NOT_FOUND for item in results),
        results=results,
    )
