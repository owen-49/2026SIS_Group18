"""Entailment verification: does the source text actually support the claim?

Uses an LLM (GPT-4o / Gemini / Claude) to judge whether a claim is:
- SUPPORT: Source text directly backs the claim.
- PARTIAL: Source text partially supports, but claim overstates or omits caveats.
- CONTRADICT: Source text disagrees with the claim.
- NOT_FOUND: The claim's content is not addressed in the source.
"""

from dataclasses import dataclass
from enum import Enum

from .retriever import RetrievalResult


class Verdict(str, Enum):
    """The relationship between a claim and its source text."""

    SUPPORT = "SUPPORT"
    PARTIAL = "PARTIAL"
    CONTRADICT = "CONTRADICT"
    NOT_FOUND = "NOT_FOUND"


@dataclass
class VerificationResult:
    """Complete verification output for a single claim."""

    claim: str
    verdict: Verdict
    confidence: float  # 0.0 - 1.0
    rationale: str
    best_match: RetrievalResult | None = None
    source_text_used: str = ""


ENTAILMENT_PROMPT = """You are a citation verification assistant for academic papers.
Your job is to determine whether a claim made in a paper is supported by the source text it cites.

SOURCE TEXT (from the cited paper):
\"\"\"
{source_passage}
\"\"\"

CLAIM (from the paper being audited):
\"\"\"
{claim}
\"\"\"

Classify the relationship as ONE of:
- SUPPORT: The source text directly supports the claim. The claim accurately represents what the source says.
- PARTIAL: The source text partially supports the claim, but the claim overstates, overgeneralizes, or omits important caveats present in the source.
- CONTRADICT: The source text contradicts or disagrees with the claim.
- NOT_FOUND: The claim's content is not addressed in the source text at all.

Respond in JSON format only:
{{"label": "SUPPORT" | "PARTIAL" | "CONTRADICT" | "NOT_FOUND", "rationale": "Brief explanation citing specific text from the source."}}
"""


class Verifier:
    """LLM-based claim verifier."""

    def __init__(self, model: str = "gpt-4o"):
        """Initialize the verifier.

        Args:
            model: OpenAI model identifier. Also supports Gemini/Claude via base_url override.
        """
        self.model = model

    def _build_prompt(self, claim: str, source_passage: str) -> str:
        """Build the entailment detection prompt.

        Args:
            claim: The claim text.
            source_passage: The source text to compare against.

        Returns:
            Formatted prompt string.
        """
        return ENTAILMENT_PROMPT.format(claim=claim, source_passage=source_passage)

    def verify(
        self,
        claim: str,
        source_passage: str,
        client=None,
    ) -> VerificationResult:
        """Verify whether a source passage supports a claim.

        Args:
            claim: The claim being checked.
            source_passage: The text from the cited source.
            client: OpenAI-compatible client (or None for mock mode).

        Returns:
            VerificationResult with verdict, confidence, and rationale.
        """
        prompt = self._build_prompt(claim, source_passage)

        if client is None:
            # Mock mode — returns NOT_FOUND for testing without API calls
            return VerificationResult(
                claim=claim,
                verdict=Verdict.NOT_FOUND,
                confidence=0.0,
                rationale="Mock mode: no LLM client provided.",
                source_text_used=source_passage,
            )

        import json

        response = client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,  # Deterministic for verification
            response_format={"type": "json_object"},
        )

        raw = response.choices[0].message.content
        try:
            parsed = json.loads(raw)
            label = parsed.get("label", "NOT_FOUND").upper()
            rationale = parsed.get("rationale", "No rationale provided.")
        except (json.JSONDecodeError, AttributeError):
            label = "NOT_FOUND"
            rationale = f"Failed to parse LLM response: {raw}"

        return VerificationResult(
            claim=claim,
            verdict=Verdict(label),
            confidence=0.85 if label != "NOT_FOUND" else 0.3,
            rationale=rationale,
            source_text_used=source_passage,
        )

    def verify_with_retrieval(
        self,
        claim: str,
        retrieval_results: list[RetrievalResult],
        client=None,
        top_n: int = 3,
    ) -> VerificationResult:
        """Verify a claim using the top-N retrieved passages.

        Uses the best-matching passage as the primary source text.

        Args:
            claim: The claim being checked.
            retrieval_results: Ranked retrieval results for this claim.
            client: OpenAI-compatible client.
            top_n: Number of top passages to include as context.

        Returns:
            VerificationResult with verdict based on the best match.
        """
        if not retrieval_results:
            return VerificationResult(
                claim=claim,
                verdict=Verdict.NOT_FOUND,
                confidence=0.0,
                rationale="No passages retrieved from the source paper.",
            )

        # Combine top-N passages as enriched context
        context = "\n\n---\n\n".join(
            f"[Passage {r.rank}, similarity={r.score:.3f}]\n{r.passage}"
            for r in retrieval_results[:top_n]
        )

        result = self.verify(claim, context, client=client)
        result.best_match = retrieval_results[0]
        return result
