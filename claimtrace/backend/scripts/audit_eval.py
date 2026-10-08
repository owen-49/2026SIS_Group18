"""Score a batch audit response against cases whose expected state is constructed.

The audit's five states are a decision over two inputs: the reference, and the
external record the lookup found. A benchmark that varies only the reference
cannot say what it measured, because the record half is supplied by a third
party that drifts. This module scores a *constructed* pair instead --- the
reference is authored and the record is pinned bytes (see ``audit_benchmark.py``)
--- so the expected state follows from the rules in ``docs/audit-contract.md``
rather than from anyone's judgement, and can be re-derived by hand.

Design notes:
- ``STATES`` is derived from :class:`AuditStatus` rather than restated, for the
  reason ``passage_eval.LABELS`` is derived from ``Verdict``: a state the
  product cannot emit must not be scoreable, and two restatements drift.
- A case carries a ``because`` --- the mechanism it expects, e.g.
  ``field_differs_stated`` or ``no_acceptable_record`` --- checked *independently
  of the status comparison*. A case whose pinned record differs in the year, but
  whose expected mechanism names the venue, must fail even though both produce
  ``METADATA_MISMATCH``; without that, a mis-pinned fixture would score as a
  passing measurement.
- The safety invariants are pass/fail, not rates. "A failed lookup is never
  reported as ``NOT_FOUND``" is a promise the product makes in
  ``docs/audit-contract.md``; a percentage of it is not a thing, and a run that
  breaks it is a bug rather than a low score. They are checked over any
  response, constructed or live.
- Ratios are ``None`` over an empty denominator, never ``0.0`` --- the
  ``metadata_eval`` convention. A state no case exercised must not read as a
  measured zero.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, get_args

from backend.src.audit_models import (
    AuditFieldCheck,
    AuditStatus,
    BibliographyAuditResponse,
    ReferenceAuditResult,
)

# Derived, never restated: the scorer's vocabulary is the product's.
STATES = tuple(status.value for status in AuditStatus)
FIELD_STATES = get_args(AuditFieldCheck.model_fields["status"].annotation)

# The four fields whose agreement decides VERIFIED, and the two optional ones a
# case may still pin an expectation for.
REQUIRED_FIELDS = ("title", "authors", "year", "venue")
FIELDS = ("title", "authors", "year", "venue", "doi")

# What a field check's detail says when the value came out of the raw text
# rather than from the reference's own structured fields. Written in
# bibliography_audit_service.recovered_details and read here, so the two are
# coupled by a constant rather than by a copy.
RECOVERED_PREFIX = "Recovered from the reference's raw text"

# The guard that stops before any provider is asked.
NO_TITLE_REASON = "No searchable title"

# A case the response carried no result for. Not an audit state: it means the
# fixture and the response disagree about what was sent, which is why it is
# named separately from the five rather than folded into NOT_FOUND.
UNMATCHED = "NO_RESULT"


# ── Cases ─────────────────────────────────────────────────────────


@dataclass
class ExpectedAudit:
    """What one case expects of the audit, and by which mechanism.

    Attributes:
        status: The expected :class:`AuditStatus` value.
        because: The mechanism that must produce it, named in :data:`MECHANISMS`.
            Checked in addition to the status, so a record pinned wrong cannot
            pass by landing on the expected state through another rule.
        field_checks: Expected ``field_name -> status``. Fields the case does
            not name are not checked; a field the case names that the response
            omits is a miss.
        matched_provider: Which provider's record must have been selected.
        forbidden_record_ids: Record ids the response must not have selected.
        lookup_attempts: The exact ``provider:outcome`` sequence the response
            must report, in order. Empty means "not checked".
        attempt_errors: Expected ``provider -> error_code``. The outcome alone
            cannot separate a transport failure from a throttled provider from
            an HTTP error --- all three are ``failed`` on the wire --- and the
            code is the only place the distinction survives.
        attempt_details: Expected ``provider -> substring of the attempt's
            detail``. A found attempt's detail names the *rule* that settled it
            --- a DOI the record matches, a title that matches exactly, a group
            of merged duplicates --- and two routes to the same state leave the
            same ``provider:found`` behind. Without this a case that means to
            exercise the identifier pre-pass would pass on the title search.
        reason_contains: A substring the result's reason must carry.
        candidates_required: Whether the result must carry candidate records.
    """

    status: str
    because: str
    field_checks: dict[str, str] = field(default_factory=dict)
    matched_provider: str = ""
    forbidden_record_ids: list[str] = field(default_factory=list)
    lookup_attempts: list[str] = field(default_factory=list)
    attempt_errors: dict[str, str] = field(default_factory=dict)
    attempt_details: dict[str, str] = field(default_factory=dict)
    reason_contains: str = ""
    candidates_required: bool = False


@dataclass
class AuditCase:
    """One constructed reference, its pinned record, and what follows from them.

    The reference is joined to its result in the response by exactly one of
    ``bib_key`` (the BibTeX entry's key), ``raw_text_contains`` (a substring of
    the entry's raw text, for PDF-shaped cases) or ``index``.
    """

    case_id: str
    input_kind: str
    expected: ExpectedAudit
    bib_key: str = ""
    raw_text_contains: str = ""
    index: int | None = None
    notes: str = ""


@dataclass
class CaseScore:
    """What one case scored."""

    case_id: str
    passed: bool
    expected_status: str
    actual_status: str
    mechanism_ok: bool
    detail: str


@dataclass
class SafetyReport:
    """The product's promises, checked as violations rather than rates."""

    not_found_with_incomplete_search: list[str] = field(default_factory=list)
    lookup_failed_without_a_failure: list[str] = field(default_factory=list)
    skipped_lookup_without_review: list[str] = field(default_factory=list)
    verified_without_a_record: list[str] = field(default_factory=list)
    not_found_with_field_checks: list[str] = field(default_factory=list)
    total_results: int = 0

    @property
    def violations(self) -> list[str]:
        return (
            self.not_found_with_incomplete_search
            + self.lookup_failed_without_a_failure
            + self.skipped_lookup_without_review
            + self.verified_without_a_record
            + self.not_found_with_field_checks
        )

    @property
    def passed(self) -> bool:
        return not self.violations


@dataclass
class AuditReport:
    """The scored run."""

    total: int
    passed: int
    failed: int
    status_accuracy: float | None
    per_state: dict[str, dict[str, Any]]
    macro_f1: float | None
    confusion: dict[str, dict[str, int]]
    field_accuracy: dict[str, dict[str, Any]]
    field_confusion: dict[str, dict[str, int]]
    safety: SafetyReport
    actual_statuses: dict[str, int]
    scores: list[CaseScore]


# ── Mechanisms ────────────────────────────────────────────────────


def _mismatches(result: ReferenceAuditResult) -> list:
    return [check for check in result.field_checks if check.status == "MISMATCH"]


def _is_recovered(check) -> bool:
    return check.detail.startswith(RECOVERED_PREFIX)


def _every_attempt_not_found(result: ReferenceAuditResult) -> bool:
    return bool(result.lookup_attempts) and all(
        attempt.outcome == "not_found" for attempt in result.lookup_attempts
    )


def _some_attempt_failed(result: ReferenceAuditResult) -> bool:
    return any(attempt.outcome == "failed" for attempt in result.lookup_attempts)


def _required_all_match(result: ReferenceAuditResult) -> bool:
    by_name = {check.field_name: check.status for check in result.field_checks}
    return all(by_name.get(name) == "MATCH" for name in REQUIRED_FIELDS)


def _agrees_but_is_not_exact(result: ReferenceAuditResult) -> bool:
    return (
        result.matched_record is not None
        and _required_all_match(result)
        and result.status is AuditStatus.NEEDS_REVIEW
    )


# Each mechanism names the rule that must have produced the state. The text is
# what a failure prints, so it says what was required and was not.
MECHANISMS: dict[str, tuple[str, Callable[[ReferenceAuditResult], bool]]] = {
    "fields_agree": (
        "every required field check is MATCH",
        lambda result: _required_all_match(result),
    ),
    "fields_agree_not_exact": (
        "every required field check agreeing on a matched record, reported for review "
        "because the exact gate withheld VERIFIED",
        _agrees_but_is_not_exact,
    ),
    "field_differs_stated": (
        "a MISMATCH on a field the reference states itself",
        lambda result: any(not _is_recovered(check) for check in _mismatches(result)),
    ),
    "field_differs_recovered": (
        "a MISMATCH on a field recovered from the reference's raw text",
        lambda result: any(_is_recovered(check) for check in _mismatches(result)),
    ),
    "no_acceptable_record": (
        "every provider completed and held no acceptable record",
        _every_attempt_not_found,
    ),
    "ambiguous_records": (
        "an ambiguous lookup: acceptable records the chain would not choose between",
        lambda result: (
            any(attempt.outcome == "ambiguous" for attempt in result.lookup_attempts)
            and bool(result.candidates)
        ),
    ),
    "provider_failed": (
        "at least one provider failed rather than answered",
        _some_attempt_failed,
    ),
    "no_searchable_title": (
        "the pre-lookup guard stopped before any provider was asked",
        lambda result: not result.lookup_attempts and NO_TITLE_REASON in result.reason,
    ),
}


# ── Loading ───────────────────────────────────────────────────────


def load_cases(path: str | Path) -> list[AuditCase]:
    """Load a case file.

    Raises:
        OSError: The file could not be read.
        ValueError: The file is not a list of well-formed cases. A loader that
            returned an empty set would report a broken fixture as a clean
            sweep, which is the one failure this instrument exists to catch.
    """
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    items = payload.get("cases") if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        raise ValueError(f"{path}: expected a list of cases")
    return [_case_from(item, path) for item in items]


def _case_from(item: Any, path: Any) -> AuditCase:
    if not isinstance(item, dict):
        raise ValueError(f"{path}: each case must be an object")
    case_id = str(item.get("case_id", "")).strip()
    if not case_id:
        raise ValueError(f"{path}: a case has no case_id")
    expected = item.get("expected")
    if not isinstance(expected, dict):
        raise ValueError(f"{path}: case {case_id} has no expected block")
    status = str(expected.get("status", "")).strip().upper()
    if status not in STATES:
        raise ValueError(
            f"{path}: case {case_id} expects status {status!r}, which is not one of "
            f"{', '.join(STATES)}"
        )
    because = str(expected.get("because", "")).strip()
    if because not in MECHANISMS:
        raise ValueError(
            f"{path}: case {case_id} names mechanism {because!r}, which is not one of "
            f"{', '.join(MECHANISMS)}"
        )
    for field_name, field_status in (expected.get("field_checks") or {}).items():
        if field_name not in FIELDS:
            raise ValueError(f"{path}: case {case_id} pins unknown field {field_name!r}")
        if field_status not in FIELD_STATES:
            raise ValueError(
                f"{path}: case {case_id} pins field {field_name} to unknown status {field_status!r}"
            )
    joins = [
        bool(str(item.get("bib_key", "")).strip()),
        bool(str(item.get("raw_text_contains", "")).strip()),
        item.get("index") is not None,
    ]
    if sum(joins) != 1:
        raise ValueError(
            f"{path}: case {case_id} must join its result by exactly one of "
            "bib_key, raw_text_contains or index"
        )
    return AuditCase(
        case_id=case_id,
        input_kind=str(item.get("input_kind", "")),
        expected=ExpectedAudit(
            status=status,
            because=because,
            field_checks={
                str(name): str(value).upper()
                for name, value in (expected.get("field_checks") or {}).items()
            },
            matched_provider=str(expected.get("matched_provider", "")),
            forbidden_record_ids=[
                str(record_id) for record_id in expected.get("forbidden_record_ids") or []
            ],
            lookup_attempts=[str(entry) for entry in expected.get("lookup_attempts") or []],
            attempt_errors={
                str(provider): str(code).upper()
                for provider, code in (expected.get("attempt_errors") or {}).items()
            },
            attempt_details={
                str(provider): str(fragment)
                for provider, fragment in (expected.get("attempt_details") or {}).items()
            },
            reason_contains=str(expected.get("reason_contains", "")),
            candidates_required=bool(expected.get("candidates_required", False)),
        ),
        bib_key=str(item.get("bib_key", "")),
        raw_text_contains=str(item.get("raw_text_contains", "")),
        index=item.get("index"),
        notes=str(item.get("notes", "")),
    )


def load_response(path: str | Path) -> BibliographyAuditResponse:
    """Load a persisted audit response."""
    return BibliographyAuditResponse.model_validate(
        json.loads(Path(path).read_text(encoding="utf-8"))
    )


def join_results(
    cases: list[AuditCase], response: BibliographyAuditResponse
) -> tuple[dict[str, ReferenceAuditResult], list[str]]:
    """Match every case to its result; return the map and the unmatched case ids."""
    by_key: dict[str, list[ReferenceAuditResult]] = {}
    for result in response.results:
        by_key.setdefault(result.entry.metadata.key or "", []).append(result)
    matched: dict[str, ReferenceAuditResult] = {}
    unmatched: list[str] = []
    claimed: set[int] = set()
    for case in cases:
        found = None
        for position, result in enumerate(response.results):
            if position in claimed:
                continue
            if case.bib_key and result.entry.metadata.key == case.bib_key:
                found = position
                break
            raw_text = result.entry.metadata.raw_text or ""
            if case.raw_text_contains and case.raw_text_contains in raw_text:
                found = position
                break
            if case.index is not None and position == case.index:
                found = position
                break
        if found is None:
            unmatched.append(case.case_id)
        else:
            claimed.add(found)
            matched[case.case_id] = response.results[found]
    return matched, unmatched


# ── Scoring ───────────────────────────────────────────────────────


def score_case(case: AuditCase, result: ReferenceAuditResult) -> CaseScore:
    """Score one case against its result: status, then mechanism, then details."""
    expected = case.expected
    actual = result.status.value
    problems: list[str] = []
    if actual != expected.status:
        problems.append(f"status {actual}, expected {expected.status}")

    mechanism_ok = True
    description, predicate = MECHANISMS[expected.because]
    try:
        mechanism_ok = bool(predicate(result))
    except Exception:  # pragma: no cover - the predicates are total
        mechanism_ok = False
    if not mechanism_ok:
        problems.append(f"mechanism {expected.because!r} not seen ({description})")

    checks_by_name = {check.field_name: check for check in result.field_checks}
    for name, want in expected.field_checks.items():
        check = checks_by_name.get(name)
        got = check.status if check else "ABSENT"
        if got != want:
            problems.append(f"field {name} {got}, expected {want}")

    if expected.matched_provider:
        got = result.matched_record.provider if result.matched_record else "no record"
        if got != expected.matched_provider:
            problems.append(f"matched provider {got!r}, expected {expected.matched_provider!r}")

    if expected.forbidden_record_ids:
        selected = result.matched_record.record_id if result.matched_record else ""
        if selected in expected.forbidden_record_ids:
            problems.append(f"selected forbidden record {selected}")

    if expected.lookup_attempts:
        got = [f"{attempt.provider}:{attempt.outcome}" for attempt in result.lookup_attempts]
        if got != expected.lookup_attempts:
            problems.append(f"attempts {got}, expected {expected.lookup_attempts}")

    if expected.attempt_errors:
        by_provider = {attempt.provider: attempt for attempt in result.lookup_attempts}
        for provider, want in expected.attempt_errors.items():
            attempt = by_provider.get(provider)
            got = attempt.error_code if attempt else "ABSENT"
            if got != want:
                problems.append(f"attempt {provider} error {got}, expected {want}")

    if expected.attempt_details:
        by_provider = {attempt.provider: attempt for attempt in result.lookup_attempts}
        for provider, want in expected.attempt_details.items():
            attempt = by_provider.get(provider)
            got = attempt.detail if attempt else "ABSENT"
            if want not in got:
                problems.append(f"attempt {provider} detail {got!r} does not contain {want!r}")

    if expected.reason_contains and expected.reason_contains not in result.reason:
        problems.append(f"reason does not contain {expected.reason_contains!r}")

    if expected.candidates_required and not result.candidates:
        problems.append("no candidate records reported")

    return CaseScore(
        case_id=case.case_id,
        passed=not problems,
        expected_status=expected.status,
        actual_status=actual,
        mechanism_ok=mechanism_ok,
        detail="; ".join(problems) if problems else "as expected",
    )


def check_safety(results: list[ReferenceAuditResult]) -> SafetyReport:
    """Check the promises that hold over any response, constructed or live.

    Each violation is reported with the entry id that broke it. The rules are
    read off ``docs/audit-contract.md`` and ``audit_reference``'s branches, and
    are stated as invariants over the *payload* so they can be checked against a
    live run's output without re-running the audit.
    """
    report = SafetyReport(total_results=len(results))
    for result in results:
        entry_id = result.entry.entry_id
        attempts = result.lookup_attempts
        if result.status is AuditStatus.NOT_FOUND:
            if not attempts or any(attempt.outcome != "not_found" for attempt in attempts):
                report.not_found_with_incomplete_search.append(entry_id)
            if result.field_checks:
                report.not_found_with_field_checks.append(entry_id)
        if result.status is AuditStatus.LOOKUP_FAILED and not any(
            attempt.outcome == "failed" for attempt in attempts
        ):
            report.lookup_failed_without_a_failure.append(entry_id)
        if not attempts and result.status is not AuditStatus.NEEDS_REVIEW:
            report.skipped_lookup_without_review.append(entry_id)
        if result.status is AuditStatus.VERIFIED:
            if result.matched_record is None or not _required_all_match(result):
                report.verified_without_a_record.append(entry_id)
    return report


def score_response(cases: list[AuditCase], response: BibliographyAuditResponse) -> AuditReport:
    """Score a whole response and summarize it."""
    matched, unmatched = join_results(cases, response)
    scores: list[CaseScore] = []
    for case in cases:
        result = matched.get(case.case_id)
        if result is None:
            scores.append(
                CaseScore(
                    case_id=case.case_id,
                    passed=False,
                    expected_status=case.expected.status,
                    actual_status=UNMATCHED,
                    mechanism_ok=False,
                    detail="no result in the response matches this case",
                )
            )
        else:
            scores.append(score_case(case, result))

    confusion: dict[str, dict[str, int]] = {state: Counter() for state in STATES}
    for score in scores:
        confusion[score.expected_status][score.actual_status] += 1

    per_state: dict[str, dict[str, Any]] = {}
    f1_values: list[float] = []
    for state in STATES:
        true_positive = sum(
            1 for score in scores if score.expected_status == state and score.actual_status == state
        )
        predicted = sum(1 for score in scores if score.actual_status == state)
        support = sum(1 for score in scores if score.expected_status == state)
        precision = _ratio(true_positive, predicted)
        recall = _ratio(true_positive, support)
        if precision is None or recall is None or precision + recall == 0:
            f1 = None if precision is None or recall is None else 0.0
        else:
            f1 = 2 * precision * recall / (precision + recall)
        if f1 is not None:
            f1_values.append(f1)
        per_state[state] = {
            "support": support,
            "predicted": predicted,
            "precision": precision,
            "recall": recall,
            "f1": f1,
        }

    field_accuracy: dict[str, dict[str, Any]] = {}
    field_confusion: dict[str, dict[str, int]] = {}
    for field_name in FIELDS:
        checked = correct = 0
        seen: Counter = Counter()
        for case in cases:
            want = case.expected.field_checks.get(field_name)
            if want is None:
                continue
            result = matched.get(case.case_id)
            check = None
            if result is not None:
                check = next(
                    (item for item in result.field_checks if item.field_name == field_name),
                    None,
                )
            got = check.status if check else "ABSENT"
            checked += 1
            correct += got == want
            seen[f"{want}->{got}"] += 1
        field_accuracy[field_name] = {
            "checked": checked,
            "correct": correct,
            "accuracy": _ratio(correct, checked),
        }
        field_confusion[field_name] = dict(seen)

    passes = sum(1 for score in scores if score.passed)
    return AuditReport(
        total=len(scores),
        passed=passes,
        failed=len(scores) - passes,
        status_accuracy=_ratio(
            sum(1 for score in scores if score.expected_status == score.actual_status),
            len(scores),
        ),
        per_state=per_state,
        macro_f1=(sum(f1_values) / len(f1_values)) if f1_values else None,
        confusion={state: dict(counts) for state, counts in confusion.items()},
        field_accuracy=field_accuracy,
        field_confusion=field_confusion,
        safety=check_safety(response.results),
        actual_statuses=dict(Counter(result.status.value for result in response.results)),
        scores=scores,
    )


# ── Rendering ─────────────────────────────────────────────────────


def render_report(report: AuditReport, *, title: str, source: str) -> str:
    """Render the report as plain text for a PR or a commit message."""
    lines = [
        f"== {title} ==",
        f"cases        : {report.total}  passed {report.passed}  failed {report.failed}",
        f"source       : {source}",
        f"accuracy     : {_percent(report.status_accuracy)}  (status, exact match)",
        f"macro F1     : {_percent(report.macro_f1)}",
        f"statuses     : {_histogram(report.actual_statuses)}",
        "",
        "per state (expected / predicted / precision / recall / F1):",
    ]
    for state in STATES:
        data = report.per_state[state]
        if data["support"] or data["predicted"]:
            lines.append(
                f"  {state:<18}{data['support']:>4}{data['predicted']:>11}"
                f"{_percent(data['precision']):>12}{_percent(data['recall']):>9}"
                f"{_percent(data['f1']):>8}"
            )
    columns = list(STATES)
    if any(row.get(UNMATCHED) for row in report.confusion.values()):
        columns.append(UNMATCHED)
    lines.append("")
    lines.append("confusion (row expected, column reported):")
    lines.append(f"  {'':<18}" + "".join(f"{column[:12]:>14}" for column in columns))
    for state in STATES:
        row = report.confusion[state]
        if sum(row.values()):
            lines.append(
                f"  {state:<18}" + "".join(f"{row.get(column, 0):>14}" for column in columns)
            )
    lines.append("")
    lines.append("field checks (cases that pin one):")
    for field_name in FIELDS:
        data = report.field_accuracy[field_name]
        if data["checked"]:
            lines.append(
                f"  {field_name:<10}{data['correct']:>4}/{data['checked']:<4}"
                f"{_percent(data['accuracy']):>9}  {_pairs(report.field_confusion[field_name])}"
            )
    lines.append("")
    safety = report.safety
    lines.append(
        f"safety       : {'all invariants hold' if safety.passed else 'VIOLATED'} "
        f"over {safety.total_results} result(s)"
    )
    if not safety.passed:
        for name, entries in (
            ("NOT_FOUND after an incomplete search", safety.not_found_with_incomplete_search),
            ("LOOKUP_FAILED with no failed attempt", safety.lookup_failed_without_a_failure),
            ("lookup skipped without NEEDS_REVIEW", safety.skipped_lookup_without_review),
            ("VERIFIED without a record", safety.verified_without_a_record),
            ("NOT_FOUND carrying field checks", safety.not_found_with_field_checks),
        ):
            if entries:
                lines.append(f"  {name}: {', '.join(entries)}")
    failures = [score for score in report.scores if not score.passed]
    if failures:
        lines.append("")
        lines.append("-- cases that did not match --")
        for score in failures:
            lines.append(f"  {score.case_id}: {score.detail}")
    return "\n".join(lines)


def report_payload(report: AuditReport) -> dict:
    """The report as JSON-serialisable data, for the measurement output file."""
    return {
        "total": report.total,
        "passed": report.passed,
        "failed": report.failed,
        "status_accuracy": report.status_accuracy,
        "macro_f1": report.macro_f1,
        "per_state": report.per_state,
        "confusion": report.confusion,
        "field_accuracy": report.field_accuracy,
        "field_confusion": report.field_confusion,
        "actual_statuses": report.actual_statuses,
        "safety": {
            "passed": report.safety.passed,
            "total_results": report.safety.total_results,
            "not_found_with_incomplete_search": report.safety.not_found_with_incomplete_search,
            "lookup_failed_without_a_failure": report.safety.lookup_failed_without_a_failure,
            "skipped_lookup_without_review": report.safety.skipped_lookup_without_review,
            "verified_without_a_record": report.safety.verified_without_a_record,
            "not_found_with_field_checks": report.safety.not_found_with_field_checks,
        },
        "scores": [asdict_score(score) for score in report.scores],
    }


def asdict_score(score: CaseScore) -> dict:
    """The score fields, named for a JSON reader rather than for dataclass use."""
    return {
        "case_id": score.case_id,
        "passed": score.passed,
        "expected_status": score.expected_status,
        "actual_status": score.actual_status,
        "mechanism_ok": score.mechanism_ok,
        "detail": score.detail,
    }


# ── Small helpers, matching the engine's report conventions ───────


def _ratio(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return numerator / denominator


def _percent(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.1f}%"


def _histogram(counts: dict[str, int]) -> str:
    if not counts:
        return "none"
    return "  ".join(f"{name}={count}" for name, count in sorted(counts.items()))


def _pairs(counts: dict[str, int]) -> str:
    """Field transitions, most common first, so the misses read before the hits."""
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return "  ".join(f"{name}={count}" for name, count in ordered)
