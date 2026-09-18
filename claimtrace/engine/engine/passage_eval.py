"""Score the retriever and the verifier against annotated claim-passage pairs.

ClaimTrace commits to two quantitative bars before the demo: the ground-truth
passage appears in the top 5 retrieved passages for at least 80% of claims, and
the four-way entailment judgement is right for at least 80% of an annotated
50-pair set. Neither number means anything without an instrument that turns a
pair set into them. This is that instrument. The pairs are the team's to
annotate; nothing here invents one.

Design notes:
- Ground truth matches as a **substring** of the retrieved passage, which is what
  the plan's reference ``evaluate()`` does (``any(gt in r[0] for r in results)``)
  and is the only workable reading: an annotator marks the sentence that carries
  the claim, and retrieval returns the paragraph containing it.
- Both sides are normalised before that comparison -- NFKC, whitespace runs
  collapsed, case folded. This is looser than a byte comparison, so the
  loosening is bounded: two strings that differ only in case or in how their
  whitespace runs are the same passage to a reader, and any other difference
  still fails to match. An annotator copying a snippet out of a PDF viewer
  cannot be expected to reproduce a line break.
- A pair whose source paper has no passages in the corpus is **unscorable**, not
  a miss. Counting it as a miss would let a PDF that was never loaded be
  reported as a retriever that failed to find it, which is the one confusion
  this metric must not make.
- An abstention is not an error. A :class:`~engine.verifier.VerificationStatus`
  other than ``JUDGED`` means the model did not judge the claim; scoring it as
  wrong would mix "the engine refused to answer" with "the engine answered
  wrongly", and only the second is what the accuracy bar is about. Those pairs
  are held out of accuracy, F1 and kappa, and *counted* instead: the report
  prints coverage beside every classification metric, because an accuracy over
  four judged pairs of fifty reads as a result and is not one.
- A pair with no label is ``unannotated`` and out of every metric, for the same
  reason an empty ``acceptable_dois`` is in :mod:`engine.metadata_eval`: an
  unannotated set must not be reportable as a measured one.
- Judgements arrive through an injected callback rather than by calling
  :class:`~engine.verifier.Verifier` here. The real verifier needs a network
  client, and keeping the arithmetic free of one is what lets every metric be
  unit-tested against numbers worked out by hand.
- ``LABELS`` is derived from :class:`~engine.verifier.Verdict` rather than
  restated. The benchmark's label vocabulary is the engine's verdict vocabulary;
  a pair annotated with a label the engine cannot emit is unscoreable, and
  deriving the tuple is what stops the two from drifting apart.
- :func:`load_pairs` raises on a missing or malformed file, unlike the rest of
  the engine. A loader that returned an empty pair set would report a broken
  file as a clean sweep, which is the one failure this instrument exists to
  catch.
"""

import json
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .verifier import Verdict

# The two bars, copied from the committed success criteria so a report can say
# "met" or "below" without a reader holding the plan open.
RECALL_AT_5_GO = 0.80
RECALL_AT_5_NO_GO = 0.50
RECALL_AT_1_GO = 0.50
RECALL_AT_1_NO_GO = 0.25
ACCURACY_GO = 0.80
F1_GO = 0.85
KAPPA_GO = 0.70

# The labels a pair may carry. Derived from the engine's own verdict set: an
# annotation this vocabulary cannot express is one the engine could never match.
LABELS = tuple(verdict.value for verdict in Verdict)

# The default retrieval depth, and the depth the Recall@5 bar is stated at.
DEFAULT_K = 5

_WHITESPACE_RUN = re.compile(r"\s+")


@dataclass
class AnnotatedPair:
    """One claim, the passage in its source that decides it, and the label.

    Attributes:
        claim: The claim as the citing paper makes it.
        source_passage: The sentence or passage in the source paper that carries
            the claim, marked by the annotator. Matched as a substring of what
            retrieval returns, so it is a snippet rather than a whole paragraph.
            Empty means the annotator has not marked one yet, which holds the
            pair out of the retrieval metrics.
        label: One of :data:`LABELS`, or empty for not yet annotated. Empty
            holds the pair out of every classification metric.
        source_paper: Which paper in the corpus the passage comes from.
        annotator: Who labelled it. Recorded because a benchmark whose labels
            have no author cannot be re-checked.
        citing_paper: The paper the claim is taken from, when it is not the
            source. Informational.
        notes: The annotator's one-sentence justification.
    """

    claim: str
    source_passage: str = ""
    label: str = ""
    source_paper: str = ""
    annotator: str = ""
    citing_paper: str = ""
    notes: str = ""


@dataclass
class RetrievalOutcome:
    """How one pair scored on retrieval.

    Attributes:
        rank: 1-based rank of the first retrieved passage containing the
            ground-truth snippet, or ``None`` when no retrieved passage contains
            it. ``None`` on a scored pair is a miss.
        retrieved: The passages returned, in rank order, for audit.
    """

    claim: str
    source_paper: str
    rank: int | None
    retrieved: list[str] = field(default_factory=list)

    @property
    def recall_at_1(self) -> bool:
        return self.rank == 1

    @property
    def recall_at_5(self) -> bool:
        return self.rank is not None and self.rank <= DEFAULT_K


@dataclass
class RetrievalReport:
    """The result of scoring retrieval over a whole annotated set."""

    total: int
    scored: int
    unscorable: list[str]
    recall_at_1: float | None
    recall_at_5: float | None
    outcomes: list[RetrievalOutcome]


@dataclass
class Judgement:
    """What the verifier said about one claim, reduced to what scoring reads."""

    predicted: str  # a Verdict value, or "" when the model did not judge
    status: str  # the VerificationStatus it reported


@dataclass
class VerdictOutcome:
    """How one pair scored on the entailment judgement."""

    claim: str
    expected: str
    predicted: str
    status: str
    correct: bool | None  # None when the pair was not judged


@dataclass
class VerdictReport:
    """The result of scoring the verifier over a whole annotated set.

    Attributes:
        judged: Pairs the model actually judged, and the denominator of every
            metric here. ``abstained`` is the rest.
        accuracy: Four-way agreement, over judged pairs only.
        f1_support_vs_rest: F1 with SUPPORT as the positive class and the other
            three folded together, over judged pairs only.
        kappa: Cohen's kappa over judged pairs, which corrects the accuracy for
            agreement a label-frequency-matched guesser would reach anyway.
        confusion: Expected label to predicted label to count, judged pairs only.
    """

    total: int
    judged: int
    abstained: int
    unannotated: int
    accuracy: float | None
    f1_support_vs_rest: float | None
    kappa: float | None
    confusion: dict[str, dict[str, int]]
    abstention_statuses: dict[str, int]
    outcomes: list[VerdictOutcome]


def load_pairs(path: str | Path) -> list[AnnotatedPair]:
    """Load an annotated pair file.

    Raises:
        OSError: The file could not be read.
        ValueError: The file is not a list of well-formed pairs.
    """
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    items = payload.get("pairs") if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        raise ValueError(f"{path}: expected a list of pairs")
    return [_pair_from(item, path) for item in items]


def _pair_from(item: Any, path: Any) -> AnnotatedPair:
    if not isinstance(item, dict):
        raise ValueError(f"{path}: each pair must be an object")
    if not str(item.get("claim", "")).strip():
        raise ValueError(f"{path}: a pair has no claim; every pair needs the claim text")
    label = str(item.get("label", "")).strip().upper()
    if label and label not in LABELS:
        raise ValueError(
            f"{path}: label {label!r} is not one of {', '.join(LABELS)}; "
            "leave it empty if the pair is not annotated yet"
        )
    return AnnotatedPair(
        claim=str(item["claim"]),
        source_passage=str(item.get("source_passage", "")),
        label=label,
        source_paper=str(item.get("source_paper", "")),
        annotator=str(item.get("annotator", "")),
        citing_paper=str(item.get("citing_paper", "")),
        notes=str(item.get("notes", "")),
    )


def normalize_text(value: str) -> str:
    """Return the comparison form of a passage or a claim.

    NFKC, whitespace runs collapsed to one space, case folded, ends trimmed. See
    the module docstring for why this is safe to apply to both sides of a
    substring test.
    """
    folded = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return _WHITESPACE_RUN.sub(" ", folded).strip()


def find_rank(ground_truth: str, retrieved: list[str]) -> int | None:
    """Return the 1-based rank of the first passage containing the ground truth.

    ``None`` means no retrieved passage contains it. An empty ground truth has no
    rank: it would match everything, which is why a pair without one is held out
    of the retrieval metrics by the caller rather than scored here.
    """
    wanted = normalize_text(ground_truth)
    if not wanted:
        return None
    for position, passage in enumerate(retrieved, start=1):
        if wanted in normalize_text(passage):
            return position
    return None


def score_retrieval(
    pairs: list[AnnotatedPair],
    passages_by_paper: dict[str, list[str]],
    retrieve: Callable[[str, list[str], int], list[str]],
) -> RetrievalReport:
    """Score retrieval over every pair that can be scored.

    The retrieval depth is :data:`DEFAULT_K` and is not a parameter. The bar is
    stated at 5, so a caller-chosen depth would make ``recall_at_5`` mean
    whatever the last caller asked for; a deeper run is a different measurement
    and belongs behind its own bar.

    Args:
        pairs: The annotated pairs.
        passages_by_paper: Source paper id to its passages, in document order.
        retrieve: ``retrieve(claim, passages, k)`` returning the top-k passages
            in rank order. Injected so the arithmetic can be measured without a
            model.

    Returns:
        A :class:`RetrievalReport`. Never raises.
    """
    outcomes: list[RetrievalOutcome] = []
    unscorable: list[str] = []

    for pair in pairs:
        passages = passages_by_paper.get(pair.source_paper) or []
        if not pair.source_passage.strip() or not passages:
            unscorable.append(pair.claim)
            continue
        retrieved = list(retrieve(pair.claim, passages, DEFAULT_K) or [])
        outcomes.append(
            RetrievalOutcome(
                claim=pair.claim,
                source_paper=pair.source_paper,
                rank=find_rank(pair.source_passage, retrieved),
                retrieved=retrieved,
            )
        )

    scored = len(outcomes)
    return RetrievalReport(
        total=len(pairs),
        scored=scored,
        unscorable=unscorable,
        recall_at_1=_ratio(sum(1 for item in outcomes if item.recall_at_1), scored),
        recall_at_5=_ratio(sum(1 for item in outcomes if item.recall_at_5), scored),
        outcomes=outcomes,
    )


def score_verdicts(
    pairs: list[AnnotatedPair],
    judge: Callable[[AnnotatedPair], Judgement],
) -> VerdictReport:
    """Score the entailment judgement over every annotated pair.

    Args:
        pairs: The annotated pairs.
        judge: ``judge(pair)`` returning a :class:`Judgement`. Injected for the
            same reason ``retrieve`` is: the real one needs a model.

    Returns:
        A :class:`VerdictReport`. Never raises.
    """
    outcomes: list[VerdictOutcome] = []
    unannotated = 0

    for pair in pairs:
        if not pair.label:
            unannotated += 1
            continue
        judgement = judge(pair)
        predicted = judgement.predicted if judgement.predicted in LABELS else ""
        outcomes.append(
            VerdictOutcome(
                claim=pair.claim,
                expected=pair.label,
                predicted=predicted,
                status=judgement.status,
                correct=None if not predicted else predicted == pair.label,
            )
        )

    judged = [item for item in outcomes if item.correct is not None]
    return VerdictReport(
        total=len(pairs),
        judged=len(judged),
        abstained=len(outcomes) - len(judged),
        unannotated=unannotated,
        accuracy=_ratio(sum(1 for item in judged if item.correct), len(judged)),
        f1_support_vs_rest=_f1_support_vs_rest(judged),
        kappa=cohen_kappa([(item.expected, item.predicted) for item in judged]),
        confusion=_confusion(judged),
        abstention_statuses=dict(
            Counter(item.status for item in outcomes if item.correct is None).most_common()
        ),
        outcomes=outcomes,
    )


def cohen_kappa(pairs: list[tuple[str, str]]) -> float | None:
    """Return Cohen's kappa for expected/predicted label pairs.

    ``None`` when no pair was scored, or when the two raters share a single label
    between them, which leaves the expected agreement at 1 and the statistic
    undefined rather than zero. Saying so is the point: a degenerate set has no
    kappa, and reporting 0.0 would read as total disagreement.
    """
    if not pairs:
        return None
    total = len(pairs)
    observed = sum(1 for expected, predicted in pairs if expected == predicted) / total
    expected_counts = Counter(expected for expected, _ in pairs)
    predicted_counts = Counter(predicted for _, predicted in pairs)
    chance = sum(
        (expected_counts[label] / total) * (predicted_counts[label] / total) for label in LABELS
    )
    if chance >= 1.0:
        return None
    return round((observed - chance) / (1.0 - chance), 4)


def bar_status(value: float | None, go: float, no_go: float | None = None) -> str:
    """Return where a metric stands against its committed bars.

    Three states where the plan states two bars, so a number between the Go line
    and the No-Go line is called what it is rather than rounded into a pass or a
    fail.
    """
    if value is None:
        return "n/a"
    if value >= go:
        return "met"
    if no_go is not None and value < no_go:
        return "no-go"
    return "below"


def render_retrieval_report(report: RetrievalReport) -> str:
    """Render a retrieval report as plain text for a commit message or a PR."""
    lines = [
        "== retrieval ==",
        f"pairs        : {report.total}  scored {report.scored}  "
        f"unscorable {len(report.unscorable)}",
        f"recall@1     : {_percent(report.recall_at_1)}"
        f"   bar >= {_percent(RECALL_AT_1_GO)}  "
        f"[{bar_status(report.recall_at_1, RECALL_AT_1_GO, RECALL_AT_1_NO_GO)}]",
        f"recall@{DEFAULT_K}     : {_percent(report.recall_at_5)}"
        f"   bar >= {_percent(RECALL_AT_5_GO)}  "
        f"[{bar_status(report.recall_at_5, RECALL_AT_5_GO, RECALL_AT_5_NO_GO)}]",
    ]
    if report.scored == 0:
        lines.append(
            "note         : nothing was scored. A pair needs a source_passage and a "
            "source_paper whose text is in the corpus."
        )
    if report.unscorable:
        lines.append(
            f"unscorable   : {len(report.unscorable)} pair(s) missing a marked passage or a "
            "loaded source paper, held out rather than counted as misses"
        )
    misses = [item for item in report.outcomes if item.rank is None]
    if misses:
        lines.append("")
        lines.append("-- ground truth not in the top-k --")
        for item in misses:
            lines.append(f"  [{item.source_paper}] {item.claim[:80]}")
    return "\n".join(lines)


def render_verdict_report(report: VerdictReport) -> str:
    """Render an entailment report as plain text for a commit message or a PR."""
    lines = [
        "== entailment ==",
        f"pairs        : {report.total}  judged {report.judged}  "
        f"abstained {report.abstained}  unannotated {report.unannotated}",
        f"coverage     : {_percent(_ratio(report.judged, report.judged + report.abstained))}"
        "   of the annotated pairs; every metric below is over the judged ones",
        f"accuracy     : {_percent(report.accuracy)}"
        f"   bar >= {_percent(ACCURACY_GO)}  [{bar_status(report.accuracy, ACCURACY_GO)}]",
        f"f1 (SUPPORT) : {_percent(report.f1_support_vs_rest)}"
        f"   bar >= {_percent(F1_GO)}  [{bar_status(report.f1_support_vs_rest, F1_GO)}]",
        f"kappa        : {_percent(report.kappa)}"
        f"   bar >= {_percent(KAPPA_GO)}  [{bar_status(report.kappa, KAPPA_GO)}]",
    ]
    if report.abstained:
        lines.append(
            f"abstentions  : {_histogram(report.abstention_statuses)} "
            "(not judged, so not scored as wrong; see the module docstring)"
        )
    if report.judged == 0:
        lines.append(
            "note         : nothing was judged. Accuracy over zero pairs is not a "
            "measurement, so none is reported."
        )
    if report.confusion:
        lines.append("")
        lines.extend(_render_confusion(report.confusion))
    wrong = [item for item in report.outcomes if item.correct is False]
    if wrong:
        lines.append("")
        lines.append("-- judged wrongly --")
        for item in wrong:
            claim = item.claim[:60]
            lines.append(f"  expected {item.expected:<10} got {item.predicted:<10} {claim}")
    return "\n".join(lines)


def _f1_support_vs_rest(judged: list[VerdictOutcome]) -> float | None:
    if not judged:
        return None
    true_positive = sum(1 for item in judged if item.expected == "SUPPORT" and item.correct)
    false_positive = sum(
        1 for item in judged if item.predicted == "SUPPORT" and item.expected != "SUPPORT"
    )
    false_negative = sum(
        1 for item in judged if item.expected == "SUPPORT" and item.predicted != "SUPPORT"
    )
    if true_positive + false_positive == 0 or true_positive + false_negative == 0:
        return None
    precision = true_positive / (true_positive + false_positive)
    recall = true_positive / (true_positive + false_negative)
    if precision + recall == 0:
        return None
    return round(2 * precision * recall / (precision + recall), 4)


def _confusion(judged: list[VerdictOutcome]) -> dict[str, dict[str, int]]:
    matrix: dict[str, dict[str, int]] = {}
    for item in judged:
        row = matrix.setdefault(item.expected, {})
        row[item.predicted] = row.get(item.predicted, 0) + 1
    return matrix


def _render_confusion(matrix: dict[str, dict[str, int]]) -> list[str]:
    width = max(len(label) for label in LABELS) + 1
    header = " " * (width + 2) + "".join(f"{label:>{width + 1}}" for label in LABELS)
    lines = ["-- confusion (expected rows, predicted columns) --", header]
    for expected in LABELS:
        row = matrix.get(expected)
        if not row:
            continue
        cells = "".join(f"{row.get(label, 0):>{width + 1}}" for label in LABELS)
        lines.append(f"  {expected:<{width}}{cells}")
    return lines


def _ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def _percent(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.1f}%"


def _histogram(counts: dict[str, int]) -> str:
    return ", ".join(f"{name}={count}" for name, count in counts.items()) or "none"
