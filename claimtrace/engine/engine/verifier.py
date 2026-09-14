"""Entailment verification: does the source text actually support the claim?

Uses an LLM (GPT-4o / Gemini / Claude) to judge whether a claim is:
- SUPPORT: Source text directly backs the claim.
- PARTIAL: Source text partially supports, but claim overstates or omits caveats.
- CONTRADICT: Source text disagrees with the claim.
- NOT_FOUND: The claim's content is not addressed in the source.

**A verdict is only ever returned when the model actually judged the claim.**
Every other outcome — no client, no usable evidence, a failed call, an unusable
reply — is reported through :class:`VerificationStatus` with ``verdict=None``.
``NOT_FOUND`` is itself a judgement ("the source does not address this"), so
substituting it for "I could not tell" fabricates a finding rather than
degrading gracefully.
"""

import json
from dataclasses import dataclass
from enum import Enum

from .retriever import RetrievalResult


class Verdict(str, Enum):
    """The relationship between a claim and its source text.

    **This enum is a closed, frozen set.** Three consumers outside this package
    treat it as exhaustive, and a fifth member would break them silently or
    loudly rather than raise anywhere near its cause:

    * ``frontend/src/components/VerdictBadge.tsx`` indexes a
      ``Record<Verdict, string>`` label map with no runtime guard, so an unknown
      member renders ``undefined`` and a bogus ``verdict-<name>`` CSS class.
    * ``frontend/src/types/api.ts`` declares the same four string literals.
    * ``backend/src/models.py`` mirrors this enum as ``VerdictEnum`` and both
      backend call sites do ``VerdictEnum(result.verdict.value)``, which raises
      ``ValueError`` for anything else.

    A failure to judge is therefore expressed by :class:`VerificationStatus`,
    never by a new verdict.
    """

    SUPPORT = "SUPPORT"
    PARTIAL = "PARTIAL"
    CONTRADICT = "CONTRADICT"
    NOT_FOUND = "NOT_FOUND"


class VerificationStatus(str, Enum):
    """Whether a verdict was produced — and if not, why not.

    ``JUDGED`` is the only member that carries a verdict. Every other member
    means *the model did not judge the claim*; none of them means the claim is
    unsupported, and none may be rendered as a verdict.
    """

    JUDGED = "JUDGED"
    """The model returned a usable label. ``verdict`` is set."""

    NO_EVIDENCE = "NO_EVIDENCE"
    """There was no usable source text to judge against — fix retrieval/parsing."""

    NO_CLIENT = "NO_CLIENT"
    """No LLM client was supplied — fix configuration (API key / ``.env``)."""

    MODEL_ERROR = "MODEL_ERROR"
    """The call itself failed (transport, provider, timeout) — retry or check upstream."""

    INVALID_LABEL = "INVALID_LABEL"
    """The reply parsed but its label was missing, blank, or outside ``Verdict``."""

    INVALID_RESPONSE = "INVALID_RESPONSE"
    """The reply was not a JSON object at all — the provider may have ignored
    ``response_format``, or the transport truncated it."""


def _has_text(value: object) -> bool:
    """True when *value* is a string holding something other than whitespace."""
    return isinstance(value, str) and bool(value.strip())


def _format_passages(results: list[RetrievalResult]) -> str:
    """Render retrieved passages as the SOURCE TEXT the model is shown."""
    return "\n\n---\n\n".join(
        f"[Passage {r.rank}, similarity={r.score:.3f}]\n{r.passage}" for r in results
    )


@dataclass
class VerificationResult:
    """Complete verification output for a single claim.

    Build these with :meth:`judged` or :meth:`failed` rather than directly. The
    two constructors cannot express an illegal combination, and
    :meth:`__post_init__` rejects one that is hand-built anyway.

    Fields:
        claim: The claim as submitted.
        status: Whether the claim was judged, and if not, why not.
        verdict: The judgement. Set **only** when ``status is JUDGED``.
        confidence: A coarse band, **not** a probability reported by the model.
            Always ``0.0`` on a failure — a failure must not imply certainty.
        rationale: Human-readable explanation, or the reason for the failure.
        best_match: The passage the verdict rests on. ``None`` unless judged.
        source_text_used: The exact source text the model was shown.
    """

    claim: str
    status: VerificationStatus
    verdict: Verdict | None = None
    confidence: float = 0.0
    rationale: str = ""
    best_match: RetrievalResult | None = None
    source_text_used: str = ""

    def __post_init__(self) -> None:
        # Also catches the old positional misuse ``VerificationResult(claim, verdict)``,
        # which used to build a result whose verdict was silently wrong.
        if not isinstance(self.status, VerificationStatus):
            raise TypeError(
                "status must be a VerificationStatus, got "
                f"{type(self.status).__name__}; build results with "
                "VerificationResult.judged() or VerificationResult.failed()"
            )
        judged = self.status is VerificationStatus.JUDGED
        if judged and self.verdict is None:
            raise ValueError("status JUDGED requires a verdict")
        if not judged and self.verdict is not None:
            raise ValueError(f"status {self.status.value} must not carry a verdict")
        if self.verdict is not None and not isinstance(self.verdict, Verdict):
            raise TypeError(f"verdict must be a Verdict, got {type(self.verdict).__name__}")

    @classmethod
    def judged(
        cls,
        *,
        claim: str,
        verdict: Verdict,
        confidence: float,
        rationale: str,
        best_match: RetrievalResult | None = None,
        source_text_used: str = "",
    ) -> "VerificationResult":
        """Build the result of a real judgement."""
        return cls(
            claim=claim,
            status=VerificationStatus.JUDGED,
            verdict=verdict,
            confidence=confidence,
            rationale=rationale,
            best_match=best_match,
            source_text_used=source_text_used,
        )

    @classmethod
    def failed(
        cls,
        *,
        claim: str,
        status: VerificationStatus,
        rationale: str,
        source_text_used: str = "",
    ) -> "VerificationResult":
        """Build a failure result: no verdict, no confidence, no best match."""
        if status is VerificationStatus.JUDGED:
            raise ValueError("status JUDGED must be built with VerificationResult.judged()")
        return cls(
            claim=claim,
            status=status,
            verdict=None,
            confidence=0.0,
            rationale=rationale,
            best_match=None,
            source_text_used=source_text_used,
        )


ENTAILMENT_PROMPT = (
    "You are a citation verification assistant for academic papers.\n"
    "Your job is to determine whether a claim made in a paper is supported by "
    "the source text it cites.\n"
    "\n"
    "SOURCE TEXT (from the cited paper):\n"
    '"""\n'
    "{source_passage}\n"
    '"""\n'
    "\n"
    "CLAIM (from the paper being audited):\n"
    '"""\n'
    "{claim}\n"
    '"""\n'
    "\n"
    "Classify the relationship as ONE of:\n"
    "- SUPPORT: The source text directly supports the claim. The claim "
    "accurately represents what the source says.\n"
    "- PARTIAL: The source text partially supports the claim, but the claim "
    "overstates, overgeneralizes, or omits important caveats present in the "
    "source.\n"
    "- CONTRADICT: The source text contradicts or disagrees with the claim.\n"
    "- NOT_FOUND: The claim's content is not addressed in the source text at "
    "all.\n"
    "\n"
    "Respond in JSON format only:\n"
    '{{"label": "SUPPORT" | "PARTIAL" | "CONTRADICT" | "NOT_FOUND", '
    '"rationale": "Brief explanation citing specific text from the source."}}\n'
)


class Verifier:
    """LLM-based claim verifier."""

    def __init__(self, model: str = "deepseek-chat"):
        """Initialize the verifier.

        Args:
            model: Model identifier. Defaults to "deepseek-chat".
                   Also supports OpenAI/Gemini/Claude models.
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

        Every failure returns ``verdict=None`` with an explanatory
        :class:`VerificationStatus`; this method never invents a verdict.

        Args:
            claim: The claim being checked.
            source_passage: The text from the cited source.
            client: OpenAI-compatible client, or ``None`` when unconfigured.

        Returns:
            VerificationResult carrying a verdict only when one was reached.
        """
        # Input validation precedes the client check, so ``verify("", "", None)``
        # reports the more fundamental fault rather than the missing client.
        if not _has_text(claim):
            return VerificationResult.failed(
                claim=claim,
                status=VerificationStatus.NO_EVIDENCE,
                rationale="No claim text was supplied, so nothing could be judged.",
                source_text_used=source_passage if isinstance(source_passage, str) else "",
            )
        if not _has_text(source_passage):
            return VerificationResult.failed(
                claim=claim,
                status=VerificationStatus.NO_EVIDENCE,
                rationale=(
                    "No source text was supplied, so the claim could not be judged "
                    "against the cited paper."
                ),
                source_text_used=source_passage if isinstance(source_passage, str) else "",
            )
        if client is None:
            return VerificationResult.failed(
                claim=claim,
                status=VerificationStatus.NO_CLIENT,
                rationale=(
                    "No LLM client was provided, so the claim was not judged. "
                    "Configure an API key and retry."
                ),
                source_text_used=source_passage,
            )

        prompt = self._build_prompt(claim, source_passage)

        try:
            response = client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,  # Deterministic for verification
                response_format={"type": "json_object"},
            )
        except Exception as exc:  # provider SDKs raise their own types
            return VerificationResult.failed(
                claim=claim,
                status=VerificationStatus.MODEL_ERROR,
                rationale=f"The language model call failed ({exc!r}).",
                source_text_used=source_passage,
            )

        try:
            raw = response.choices[0].message.content
        except (AttributeError, IndexError, TypeError) as exc:
            return VerificationResult.failed(
                claim=claim,
                status=VerificationStatus.INVALID_RESPONSE,
                rationale=f"The language model reply had no readable content ({exc!r}).",
                source_text_used=source_passage,
            )

        if not _has_text(raw):
            return VerificationResult.failed(
                claim=claim,
                status=VerificationStatus.INVALID_RESPONSE,
                rationale=(
                    "The language model returned no text content "
                    f"(got {type(raw).__name__}); there is no label to read."
                ),
                source_text_used=source_passage,
            )

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return VerificationResult.failed(
                claim=claim,
                status=VerificationStatus.INVALID_RESPONSE,
                rationale=f"Failed to parse LLM response as JSON: {raw}",
                source_text_used=source_passage,
            )

        if not isinstance(parsed, dict):
            return VerificationResult.failed(
                claim=claim,
                status=VerificationStatus.INVALID_RESPONSE,
                rationale=(
                    f"Failed to parse LLM response as a JSON object: {raw}"
                ),
                source_text_used=source_passage,
            )

        label = parsed.get("label")
        if not _has_text(label):
            return VerificationResult.failed(
                claim=claim,
                status=VerificationStatus.INVALID_LABEL,
                rationale=(
                    "The language model reply contained no usable 'label' field: "
                    f"{raw}"
                ),
                source_text_used=source_passage,
            )

        try:
            verdict = Verdict(label.strip().upper())
        except ValueError:
            expected = ", ".join(member.value for member in Verdict)
            return VerificationResult.failed(
                claim=claim,
                status=VerificationStatus.INVALID_LABEL,
                rationale=(
                    f"The language model returned an unrecognised label "
                    f"{label.strip()!r}; expected one of {expected}."
                ),
                source_text_used=source_passage,
            )

        rationale = parsed.get("rationale")
        return VerificationResult.judged(
            claim=claim,
            verdict=verdict,
            confidence=0.85 if verdict is not Verdict.NOT_FOUND else 0.3,
            rationale=rationale if _has_text(rationale) else "No rationale provided.",
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

        Only passages that actually contain text are sent, and only those count
        toward *top_n* — a blank passage must not consume a slot and leave the
        model reading an empty frame.

        Args:
            claim: The claim being checked.
            retrieval_results: Ranked retrieval results for this claim.
            client: OpenAI-compatible client.
            top_n: Maximum number of passages to include as context.

        Returns:
            VerificationResult carrying a verdict only when one was reached.
        """
        results = list(retrieval_results) if retrieval_results else []
        limit = top_n if isinstance(top_n, int) and top_n > 0 else 0

        if limit == 0:
            return VerificationResult.failed(
                claim=claim,
                status=VerificationStatus.NO_EVIDENCE,
                rationale=(
                    f"No passages were requested for verification (top_n={top_n!r}); "
                    "the claim was not judged."
                ),
            )

        usable = [r for r in results if _has_text(getattr(r, "passage", None))][:limit]
        if not usable:
            return VerificationResult.failed(
                claim=claim,
                status=VerificationStatus.NO_EVIDENCE,
                rationale=(
                    f"No usable source passage was available ({len(results)} retrieved, "
                    "none containing text); the claim was not judged."
                ),
            )

        context = _format_passages(usable)
        result = self.verify(claim, context, client=client)
        if result.status is VerificationStatus.JUDGED:
            # best_match means "the passage the verdict rests on", so only a
            # judged result may carry one.
            result.best_match = usable[0]
        return result
