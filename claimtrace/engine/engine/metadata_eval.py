"""Score the identity rule against an annotated set of real references.

The thresholds in :mod:`engine.identity` are supposed to be measured rather than
chosen. This module is what measures them: it holds the annotated cases, scores
the rule against them, and sweeps a threshold across a range reporting every
case whose outcome changes.

Design notes:
- A case passes on more than its status. ``forbidden_dois`` exists because a
  rule that answers ``found`` on the right reference while selecting a
  superseded or fabricated record is wrong in the way that matters, and a
  status-only check would score it correct.
- ``acceptable_dois`` being empty means "not yet annotated", which is not the
  same as "no right answer". Such a case is counted separately and kept out of
  the precision and recall denominators, so an unannotated fixture cannot be
  reported as a measured one.
- Precision and recall are computed over the cases that expect a publication
  against the cases that do not, treating a ``found`` answer as a positive
  prediction. Cases expecting ``ambiguous`` are scored for pass or fail but stay
  out of both, because they are neither.
- A case may carry its own candidate set; everything else is scored against the
  recording of what the providers actually returned. Only a case whose subject
  is a response the providers do not return needs its own, and keeping that
  distinction visible is what stops a hand-written record being mistaken for
  measured evidence.
- :func:`sweep_threshold` rewrites a module constant in
  :mod:`engine.identity` for the duration of a measurement and restores it
  afterwards. That is deliberate: it measures the constant the rule actually
  reads, rather than a copy threaded through an argument that could drift from
  it.
- :func:`load_cases` raises on a missing or malformed fixture, unlike the rest
  of the engine. A loader that returned an empty case set would report a broken
  fixture as a clean sweep, which is the one failure this harness exists to
  catch.
"""

import json
from collections import Counter
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from . import identity
from .identity import PublicationCandidate, ReferenceQuery, select_identity
from .reference_text import parse_reference_text
from .title_matching import normalize_doi


@dataclass
class ExpectedIdentity:
    """What the annotated answer is for one reference.

    The identifier lists name a record the way the report names it: its DOI when
    it has one, and otherwise its provider record id. Both sides of every
    comparison go through :func:`_identity_key`, so an entry may be written in
    whichever form the provider uses -- a bare DOI, a ``https://doi.org/`` URL,
    or an OpenAlex work id.
    """

    status: str  # "found" | "ambiguous" | "not_found"
    acceptable_dois: list[str] = field(default_factory=list)
    forbidden_dois: list[str] = field(default_factory=list)
    forbidden_doi_prefixes: list[str] = field(default_factory=list)
    notes: str = ""


@dataclass
class EvalCase:
    """One annotated reference.

    Attributes:
        candidates: The records to score this case against, when the case
            carries its own. ``None`` means the recorded set for this case id,
            which is how every case drawn from a live query works. A case
            supplies its own only when there is nothing to record: its point is
            a response the providers do not return, such as a fabricated record
            arriving on its own rather than among four real ones.
    """

    case_id: str
    source_file: str
    source_number: int
    raw_text: str
    query: ReferenceQuery
    expected: ExpectedIdentity
    candidates: list[PublicationCandidate] | None = None


@dataclass
class CaseScore:
    """How one case scored, with enough detail to argue about it."""

    case_id: str
    passed: bool
    expected_status: str
    actual_status: str
    rule: str
    selected_id: str
    detail: str


@dataclass
class EvalReport:
    """The result of scoring a whole annotated set."""

    total: int
    passed: int
    failed: int
    precision: float | None
    recall: float | None
    unannotated: int
    rules: dict[str, int]
    actual_statuses: dict[str, int]
    scores: list[CaseScore]


@dataclass
class SweepPoint:
    """One threshold value's worth of scoring."""

    value: float
    passed: int
    total: int
    precision: float | None
    recall: float | None
    flips: list[str]


def load_cases(path: str | Path) -> list[EvalCase]:
    """Load the annotated fixture.

    Raises:
        OSError: The fixture could not be read.
        ValueError: The fixture is not a list of well-formed cases.
    """
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    cases = payload.get("cases") if isinstance(payload, dict) else payload
    if not isinstance(cases, list):
        raise ValueError(f"{path}: expected a list of cases")
    return [_case_from(item, path) for item in cases]


def _case_from(item: Any, path: Any) -> EvalCase:
    if not isinstance(item, dict):
        raise ValueError(f"{path}: each case must be an object")
    try:
        case_id = str(item["case_id"])
        query = item["query"]
        expected = item["expected"]
    except KeyError as exc:
        raise ValueError(f"{path}: case is missing {exc}") from exc
    if not isinstance(query, dict) or not isinstance(expected, dict):
        raise ValueError(f"{path}: {case_id} has a malformed query or expected block")
    inline = item.get("candidates")
    return EvalCase(
        case_id=case_id,
        source_file=str(item.get("source_file", "")),
        source_number=int(item.get("source_number", 0)),
        raw_text=str(item.get("raw_text", "")),
        query=ReferenceQuery(**query),
        expected=ExpectedIdentity(**expected),
        candidates=(
            [candidate_from_dict(entry) for entry in inline] if isinstance(inline, list) else None
        ),
    )


def candidates_for(
    case: EvalCase,
    recordings: dict[str, list[PublicationCandidate]],
) -> list[PublicationCandidate]:
    """Return the records to score a case against.

    A case that carries its own candidates wins over the recordings directory.
    The two are not interchangeable: a recorded set is what the providers
    returned, and a case carrying its own is one whose subject is a response the
    providers do not return.
    """
    if case.candidates is not None:
        return case.candidates
    return recordings.get(case.case_id, [])


def query_for(case: EvalCase, source: str) -> ReferenceQuery:
    """Return the query to score a case with.

    Args:
        case: The annotated case.
        source: ``"fixture"`` for the hand-checked query block, or ``"parsed"``
            to derive it from the raw text. Scoring the fixture's own query
            separates a mistake in the identity rule from a mistake in reference
            parsing; scoring the parsed one measures the pair.
    """
    if source == "parsed":
        return parse_reference_text(case.raw_text)
    if source != "fixture":
        raise ValueError(f"unknown query source: {source}")
    return case.query


def score_case(case: EvalCase, candidates: list[PublicationCandidate], *, source: str = "fixture"):
    """Score one case against the records a provider returned for it."""
    query = query_for(case, source)
    decision = select_identity(query, candidates)
    selected_id = _candidate_identity(decision.selected) if decision.selected else ""
    expected = case.expected

    if decision.selected is not None and _is_forbidden(selected_id, expected):
        return CaseScore(
            case_id=case.case_id,
            passed=False,
            expected_status=expected.status,
            actual_status=decision.status,
            rule=decision.rule,
            selected_id=selected_id,
            detail=f"selected a forbidden record: {selected_id}",
        )
    if decision.status != expected.status:
        return CaseScore(
            case_id=case.case_id,
            passed=False,
            expected_status=expected.status,
            actual_status=decision.status,
            rule=decision.rule,
            selected_id=selected_id,
            detail=f"expected {expected.status}, got {decision.status}: {decision.reason}",
        )
    if decision.status == "found" and expected.acceptable_dois:
        acceptable = {_identity_key(doi) for doi in expected.acceptable_dois}
        if _identity_key(selected_id) not in acceptable:
            return CaseScore(
                case_id=case.case_id,
                passed=False,
                expected_status=expected.status,
                actual_status=decision.status,
                rule=decision.rule,
                selected_id=selected_id,
                detail=f"selected {selected_id}, which is not an acceptable answer",
            )
    return CaseScore(
        case_id=case.case_id,
        passed=True,
        expected_status=expected.status,
        actual_status=decision.status,
        rule=decision.rule,
        selected_id=selected_id,
        detail=decision.reason,
    )


def score_all(cases, recordings, *, source: str = "fixture") -> list[CaseScore]:
    """Score every case against its candidates."""
    return [score_case(case, candidates_for(case, recordings), source=source) for case in cases]


def summarize(cases: list[EvalCase], scores: list[CaseScore]) -> EvalReport:
    """Reduce per-case scores to a report."""
    by_id = {case.case_id: case for case in cases}
    true_positive = false_positive = false_negative = 0
    unannotated = 0

    for score in scores:
        case = by_id.get(score.case_id)
        expected = case.expected if case else None
        annotated = bool(expected and expected.acceptable_dois)
        if score.actual_status == "found":
            if expected is not None and expected.status == "found":
                if annotated:
                    if score.passed:
                        true_positive += 1
                    else:
                        false_positive += 1
                else:
                    unannotated += 1
            else:
                false_positive += 1
        elif expected is not None and expected.status == "found" and annotated:
            false_negative += 1

    return EvalReport(
        total=len(scores),
        passed=sum(1 for score in scores if score.passed),
        failed=sum(1 for score in scores if not score.passed),
        precision=_ratio(true_positive, true_positive + false_positive),
        recall=_ratio(true_positive, true_positive + false_negative),
        unannotated=unannotated,
        rules=dict(Counter(score.rule for score in scores if score.rule).most_common()),
        actual_statuses=dict(Counter(score.actual_status for score in scores).most_common()),
        scores=scores,
    )


def sweep_values(start: float, stop: float, step: float) -> list[float]:
    """Return the values from ``start`` to ``stop`` inclusive.

    Computed in hundredths so that a sweep prints 0.70 rather than 0.7000000001.
    """
    low, high, stride = round(start * 100), round(stop * 100), round(step * 100)
    if stride <= 0:
        raise ValueError("step must be positive")
    return [value / 100 for value in range(low, high + 1, stride)]


def sweep_threshold(
    cases: list[EvalCase],
    recordings: dict[str, list[PublicationCandidate]],
    values: list[float],
    *,
    attribute: str = "YEAR_TOLERANCE",
    source: str = "fixture",
) -> list[SweepPoint]:
    """Re-score the annotated set at each threshold value.

    The constant named by ``attribute`` is rewritten in :mod:`engine.identity`
    for the duration of each measurement and restored afterwards, so what is
    measured is the value the rule reads.
    """
    points: list[SweepPoint] = []
    previous: dict[str, bool] = {}
    for value in values:
        with _temporarily(attribute, value):
            scores = score_all(cases, recordings, source=source)
        report = summarize(cases, scores)
        current = {score.case_id: score.passed for score in scores}
        flips = sorted(
            case_id
            for case_id, passed in current.items()
            if case_id in previous and previous[case_id] != passed
        )
        points.append(
            SweepPoint(
                value=value,
                passed=report.passed,
                total=report.total,
                precision=report.precision,
                recall=report.recall,
                flips=flips,
            )
        )
        previous = current
    return points


@contextmanager
def _temporarily(attribute: str, value: float):
    original = getattr(identity, attribute)
    setattr(identity, attribute, value)
    try:
        yield
    finally:
        setattr(identity, attribute, original)


def render_report(report: EvalReport, *, title: str, source: str) -> str:
    """Render a scoring report as plain text for a commit message or a PR."""
    lines = [
        f"== {title} ==",
        f"query source : {source}",
        f"cases        : {report.total}  passed {report.passed}  failed {report.failed}",
        f"precision    : {_percent(report.precision)}",
        f"recall       : {_percent(report.recall)}",
    ]
    if report.unannotated:
        lines.append(
            f"unannotated  : {report.unannotated} case(s) answered found with no "
            f"acceptable_dois to check against, excluded from precision and recall"
        )
    lines.append(f"rules        : {_histogram(report.rules)}")
    lines.append(f"statuses     : {_histogram(report.actual_statuses)}")
    failures = [score for score in report.scores if not score.passed]
    if failures:
        lines.append("")
        lines.append("-- failures --")
        for score in failures:
            lines.append(f"  {score.case_id}: {score.detail}")
    return "\n".join(lines)


def render_sweep(points: list[SweepPoint], *, attribute: str) -> str:
    """Render a threshold sweep as plain text."""
    lines = [
        f"== sweep of {attribute} ==",
        f"{'value':>6}  {'passed':>7}  {'precision':>9}  {'recall':>7}  flips",
    ]
    for point in points:
        flips = ", ".join(point.flips) if point.flips else "-"
        lines.append(
            f"{point.value:>6.2f}  {point.passed:>3}/{point.total:<3}  "
            f"{_percent(point.precision):>9}  {_percent(point.recall):>7}  {flips}"
        )
    return "\n".join(lines)


def candidate_to_dict(candidate: PublicationCandidate) -> dict:
    """Return the recorded form of a candidate."""
    return asdict(candidate)


def candidate_from_dict(payload: dict) -> PublicationCandidate:
    """Rebuild a candidate from its recorded form."""
    return PublicationCandidate(**payload)


def load_recordings(directory: str | Path) -> dict[str, list[PublicationCandidate]]:
    """Load every recorded candidate set in a directory, keyed by case id."""
    recordings: dict[str, list[PublicationCandidate]] = {}
    for path in sorted(Path(directory).glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        items = payload.get("candidates") if isinstance(payload, dict) else payload
        recordings[path.stem] = [candidate_from_dict(item) for item in items or []]
    return recordings


def save_recording(directory: str | Path, case_id: str, payload: dict) -> Path:
    """Write one case's recorded candidates and return the path written."""
    target = Path(directory)
    target.mkdir(parents=True, exist_ok=True)
    path = target / f"{case_id}.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _candidate_identity(candidate: PublicationCandidate) -> str:
    """Return the identifier a report should show for a candidate.

    The DOI when there is one, since that is what a person would cite, and the
    provider's record id otherwise. Only for display; every comparison goes
    through :func:`_identity_key`.
    """
    return candidate.doi.strip() or candidate.record_id.strip()


def _identity_key(value: str) -> str:
    """Return the comparison form of an identifier, DOI or record id alike.

    A record with no DOI is named by something like ``W2963472678``, which is
    not a DOI and is not normalised like one; applying the same function to both
    sides is what keeps the two comparable instead of comparing a raw id against
    a normalised one.
    """
    return normalize_doi(value)


def _is_forbidden(selected_id: str, expected: ExpectedIdentity) -> bool:
    if not selected_id:
        return False
    key = _identity_key(selected_id)
    if key in {_identity_key(doi) for doi in expected.forbidden_dois}:
        return True
    return any(
        key.startswith(_identity_key(prefix))
        for prefix in expected.forbidden_doi_prefixes
        if prefix.strip()
    )


def _ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def _percent(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.1f}%"


def _histogram(counts: dict[str, int]) -> str:
    return ", ".join(f"{name}={count}" for name, count in counts.items()) or "none"
