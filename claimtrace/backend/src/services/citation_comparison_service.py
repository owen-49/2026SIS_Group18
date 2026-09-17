"""Compare one manuscript claim against the paper it cites.

The pipeline is: resolve the claim's citation marker to a parsed source paper
(:mod:`source_locator`), embed and semantically retrieve the passages most
relevant to the claim (Engine ``Retriever``), then ask the LLM whether those
passages actually support the claim (Engine ``Verifier``).

The Engine distinguishes a judgement from a failure to judge:
``VerificationResult.verdict`` is set only when ``status is JUDGED``, and every
other status says why no judgement was reached. This module maps those statuses
onto ``ComparisonStatus`` instead of letting a missing verdict read as one.

The empty-retrieval guard below is now defence in depth — the Engine reports
``NO_EVIDENCE`` for itself — but refusing the work outright is both cheaper and
independent of Engine behaviour.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..config import get_settings
from ..models import (
    CitationComparisonResponse,
    ComparisonEvidence,
    ComparisonJudgement,
    ComparisonStatus,
    SourceDocument,
    VerdictEnum,
)
from . import engine_adapter
from .paper_lifecycle import paper_lifecycle_lock
from .source_locator import (
    CitationLookup,
    SourceLocatorError,
    locate_source,
    look_up_citation,
    parse_source,
)

if TYPE_CHECKING:  # pragma: no cover - import cost only
    from engine.retriever import Retriever


class CitationComparisonError(RuntimeError):
    """Raised when a comparison cannot be performed at all."""


class ComparisonLLMNotConfiguredError(RuntimeError):
    """Raised when no LLM provider is configured, making a verdict impossible."""


def _new_retriever() -> Retriever:
    """Build a per-request retriever over the shared, cached embedder.

    Test seam. The embedder is cached process-wide because loading the model
    costs seconds; the retriever is emphatically *not*, because ``build_index``
    mutates it in place — sharing one across requests would let concurrent
    comparisons search each other's document, which fails silently rather than
    raising. The import is deferred so this module stays cheap to import at
    application start-up.
    """
    from engine.retriever import Retriever

    return Retriever(embedder=engine_adapter._get_embedder())


def _clamp_similarity(score: float) -> float:
    """Clamp a retrieval score into the response model's ``[0, 1]`` range.

    The retriever uses ``IndexFlatIP`` over L2-normalised embeddings, so the
    inner product is a cosine similarity and *can be negative* for unrelated
    text (measured: -0.105). ``ComparisonEvidence.similarity`` is bounded below
    by zero, so the raw score would otherwise fail validation with a 500.
    """
    return max(0.0, min(1.0, float(score)))


def _build_evidence(
    retrieval: list,
    lookup: CitationLookup,
) -> list[ComparisonEvidence]:
    """Attach page and display provenance to each retrieved passage.

    ``RetrievalResult.passage_index`` indexes the passage list handed to
    ``build_index``, which ``source_locator.source_passages`` guarantees is
    positionally identical to ``parsed.paragraphs``. That equality is the only
    reason a passage can be traced back to a page.
    """
    assert lookup.source is not None  # guarded by the caller
    paragraphs = lookup.source.parsed.paragraphs
    locations = lookup.source.view.paragraph_locations

    evidence: list[ComparisonEvidence] = []
    for result in retrieval:
        index = result.passage_index
        if not 0 <= index < len(paragraphs):
            # Defensive: an out-of-range index would otherwise be an IndexError
            # raised far from its cause.
            continue
        evidence.append(
            ComparisonEvidence(
                passage_text=result.passage,
                page=max(1, paragraphs[index].page_start),
                similarity=_clamp_similarity(result.score),
                rank=result.rank,
                location=locations.get(index),
            )
        )
    return evidence


def _source_document(lookup: CitationLookup, evidence: list[ComparisonEvidence]) -> SourceDocument:
    """Return the source paper's display view, highlighted at the best passage."""
    assert lookup.source is not None  # guarded by the caller
    document = lookup.source.view.document
    top_location = next((item.location for item in evidence if item.location), None)
    if top_location is None:
        return document
    return document.model_copy(update={"matched_location": top_location})


def compare_claim_to_cited_paper(
    *,
    claim: str,
    citation_marker: str,
    manuscript_id: str | None = None,
    bib_paper_id: str | None = None,
    claim_id: str | None = None,
    k: int = 5,
) -> CitationComparisonResponse:
    """Compare a claim against the paper its citation marker points at.

    Every failure that still yields useful information is reported as a
    ``ComparisonStatus`` on a 200 response, not as an HTTP error — the caller
    gets the resolved source and retrieved evidence even when no verdict was
    produced. Only two conditions are raised:

    Raises:
        CitationComparisonError: The claim was empty, or the paper library could
            not be read.
        ComparisonLLMNotConfiguredError: No LLM API key is configured. This is a
            deployment fault and is reported as such rather than silently
            degraded — without a client the Engine cannot judge anything, and a
            comparison reporting "not judged" as though it were a verdict would
            be worse than no comparison at all.
    """
    clean_claim = claim.strip()
    if not clean_claim:
        raise CitationComparisonError("Claim text is required.")

    settings = get_settings()
    if not settings.is_llm_configured:
        raise ComparisonLLMNotConfiguredError(
            f"No API key is configured for LLM provider '{settings.llm_provider}'."
        )

    try:
        lookup = look_up_citation(
            citation_marker, exclude_paper_id=manuscript_id, bib_paper_id=bib_paper_id
        )
    except SourceLocatorError as exc:
        raise CitationComparisonError("Unable to read the paper library.") from exc

    base: dict = {
        "claim": clean_claim,
        "citation_marker": lookup.marker,
        "citation_key": lookup.citation_key,
        "claim_id": claim_id,
        "cited_source": lookup.cited_source,
        "source_paper_id": lookup.source.record.paper_id if lookup.source else None,
    }

    if not lookup.resolved:
        return CitationComparisonResponse(status=lookup.outcome, message=lookup.message, **base)

    # ── Resolve: index the source paper and retrieve evidence ──
    # The lock keeps a concurrent DELETE /api/papers/{id} from removing the
    # parsed output between locating this paper and finishing with it.
    with paper_lifecycle_lock(lookup.source.record.paper_id):
        from engine.source_resolver import SourceResolver

        resolver = SourceResolver(
            locate=lambda key: locate_source(key, lookup=lookup),
            parse=parse_source,
            retriever=_new_retriever(),
        )
        resolved = resolver.resolve(clean_claim, lookup.citation_key or lookup.marker, k=k)

    if not resolved.resolved:
        return CitationComparisonResponse(
            status=ComparisonStatus.SOURCE_NOT_AVAILABLE,
            message=resolved.reason or lookup.message,
            **base,
        )
    if not resolved.retrieval:
        # Defence in depth. The Engine now reports NO_EVIDENCE rather than a
        # verdict for this case, but there is no reason to pay for an embedding
        # round trip to learn what we already know.
        return CitationComparisonResponse(
            status=ComparisonStatus.SOURCE_EMPTY,
            message="The cited paper parsed without any passage to compare against.",
            source_document=_source_document(lookup, []),
            **base,
        )

    evidence = _build_evidence(resolved.retrieval, lookup)
    source_document = _source_document(lookup, evidence)

    # ── Judge: real LLM verdict ────────────────────────────────
    client = engine_adapter._get_llm_client()
    if client is None:
        raise ComparisonLLMNotConfiguredError(
            f"The LLM client for provider '{settings.llm_provider}' could not be built."
        )

    from engine.verifier import VerificationStatus, Verifier

    verifier = Verifier(model=settings.llm_model_name)
    try:
        result = verifier.verify_with_retrieval(
            clean_claim, resolved.retrieval, client=client, top_n=3
        )
        if result.status is not VerificationStatus.JUDGED:
            # The Engine says it did not judge the claim. Reporting that as a
            # verdict would fabricate a finding, so it becomes a status of its
            # own. ``message`` carries the Engine's rationale so the reason is
            # visible to the caller rather than collapsed into a code.
            return CitationComparisonResponse(
                status=(
                    ComparisonStatus.SOURCE_EMPTY
                    if result.status is VerificationStatus.NO_EVIDENCE
                    else ComparisonStatus.LLM_FAILED
                ),
                message=result.rationale,
                source_document=source_document,
                evidence=evidence,
                **base,
            )
        judgement = ComparisonJudgement(
            verdict=VerdictEnum(result.verdict.value),
            confidence=_clamp_similarity(result.confidence),
            rationale=result.rationale,
        )
    except Exception as exc:
        # Safety net only. The Engine now reports its own failures as statuses
        # instead of raising, so anything arriving here is genuinely unexpected
        # — a provider SDK failing mid-flight, or a bug in this service.
        return CitationComparisonResponse(
            status=ComparisonStatus.LLM_FAILED,
            message=f"The language model did not return a usable verdict ({exc}).",
            source_document=source_document,
            evidence=evidence,
            **base,
        )

    return CitationComparisonResponse(
        status=ComparisonStatus.COMPARED,
        message=(
            f"Compared the claim against {len(evidence)} passage(s) retrieved "
            f"from '{resolved.title or lookup.citation_key}'."
        ),
        source_document=source_document,
        evidence=evidence,
        judgement=judgement,
        **base,
    )
