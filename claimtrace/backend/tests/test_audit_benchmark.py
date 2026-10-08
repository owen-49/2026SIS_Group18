"""Tests for audit_eval.py — the batch-audit benchmark instrument.

Every number here is worked out by hand from a constructed response, so a
failure means the arithmetic moved rather than that the audit did. The safety
invariants each get a passing and a breaking example: an invariant that cannot
fail is not being checked.
"""

import json

import pytest
from backend.scripts.audit_eval import (
    MECHANISMS,
    RECOVERED_PREFIX,
    STATES,
    UNMATCHED,
    check_safety,
    load_cases,
    render_report,
    report_payload,
    score_response,
)
from backend.src.audit_models import (
    AuditFieldCheck,
    AuditStatus,
    BibliographyAuditResponse,
    ExternalRecord,
    LookupAttempt,
    ReferenceAuditResult,
    ReferenceEntry,
)
from backend.src.models import BibEntryRecord

_REQUIRED = ("title", "authors", "year", "venue")


# --- Builders -------------------------------------------------------------------


def _entry(key, *, raw_text="", title=""):
    return ReferenceEntry(
        entry_id=f"entry-{key}",
        metadata=BibEntryRecord(
            key=key, raw_text=raw_text, title=title, authors=["A. Author"], year=2020
        ),
        metadata_source="bibtex",
    )


def _result(
    key,
    status,
    *,
    field_checks=(),
    matched_record=None,
    candidates=(),
    attempts=(),
    reason="",
    raw_text="",
    title="",
):
    return ReferenceAuditResult(
        entry=_entry(key, raw_text=raw_text, title=title),
        status=status,
        reason=reason,
        field_checks=list(field_checks),
        matched_record=matched_record,
        candidates=list(candidates),
        lookup_attempts=list(attempts),
    )


def _check(field_name, status, detail=""):
    return AuditFieldCheck(
        field_name=field_name, input_value="in", source_value="src", status=status, detail=detail
    )


def _attempt(provider, outcome, error_code=None, detail=""):
    return LookupAttempt(provider=provider, outcome=outcome, error_code=error_code, detail=detail)


def _record(provider="openalex", record_id="W1"):
    return ExternalRecord(
        provider=provider,
        record_id=record_id,
        url="https://example.org/record",
        retrieved_at="2026-01-01T00:00:00Z",
        metadata={"title": "T"},
    )


def _response(*results):
    return BibliographyAuditResponse(
        audit_id="audit-1",
        input_paper_id="paper-1",
        input_type="bib",
        checked_at="2026-01-01T00:00:00Z",
        status="completed",
        total_entries=len(results),
        counts={},
        results=list(results),
    )


def _load(tmp_path, payload):
    path = tmp_path / "cases.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return load_cases(path)


def _case(case_id, expected, **joins):
    return {"case_id": case_id, "input_kind": "bib", "expected": expected, **joins}


# --- The vocabulary is the product's --------------------------------------------


def test_the_state_vocabulary_is_the_contracts_own():
    assert STATES == (
        "VERIFIED",
        "METADATA_MISMATCH",
        "NEEDS_REVIEW",
        "NOT_FOUND",
        "LOOKUP_FAILED",
    )


def test_every_mechanism_is_named_and_described():
    assert set(MECHANISMS) == {
        "fields_agree",
        "fields_agree_not_exact",
        "field_differs_stated",
        "field_differs_recovered",
        "no_acceptable_record",
        "ambiguous_records",
        "provider_failed",
        "no_searchable_title",
    }
    for name, (description, predicate) in MECHANISMS.items():
        assert description and callable(predicate), name


# --- One hand-worked run --------------------------------------------------------


def _benchmark_set(tmp_path):
    """Four cases: three right, one wrong, with every ratio computed by hand.

    A is VERIFIED and agrees; B is a stated year mismatch; C expects a mismatch
    recovered from the raw text but the response answered NOT_FOUND; D expects
    NOT_FOUND after two empty searches and gets it.

    accuracy 3/4; VERIFIED support 1, predicted 1, F1 1.0; METADATA_MISMATCH
    support 2 (B and C), predicted 1, so precision 1.0, recall 0.5, F1 2/3;
    NOT_FOUND support 1 (D), predicted 2 (C landed here too), so precision 0.5,
    recall 1.0, F1 2/3; macro F1 = (1 + 2/3 + 2/3)/3 = 0.778.
    """
    cases = _load(
        tmp_path,
        [
            _case(
                "A-exact",
                {
                    "status": "VERIFIED",
                    "because": "fields_agree",
                    "field_checks": {name: "MATCH" for name in _REQUIRED},
                    "matched_provider": "openalex",
                },
                bib_key="A",
            ),
            _case(
                "B-year-off-by-one",
                {
                    "status": "METADATA_MISMATCH",
                    "because": "field_differs_stated",
                    "field_checks": {"year": "MISMATCH"},
                },
                bib_key="B",
            ),
            _case(
                "C-recovered-venue",
                {
                    "status": "METADATA_MISMATCH",
                    "because": "field_differs_recovered",
                    "field_checks": {"year": "MISMATCH"},
                },
                bib_key="C",
            ),
            _case(
                "D-both-empty",
                {
                    "status": "NOT_FOUND",
                    "because": "no_acceptable_record",
                    "lookup_attempts": ["openalex:not_found", "crossref:not_found"],
                },
                bib_key="D",
            ),
        ],
    )
    response = _response(
        _result(
            "A",
            AuditStatus.VERIFIED,
            matched_record=_record(),
            field_checks=[_check(name, "MATCH") for name in _REQUIRED],
            attempts=[_attempt("openalex", "found")],
            reason="The record agrees with the reference.",
        ),
        _result(
            "B",
            AuditStatus.METADATA_MISMATCH,
            matched_record=_record(record_id="W2"),
            field_checks=[_check("year", "MISMATCH")],
            attempts=[_attempt("openalex", "found")],
        ),
        _result(
            "C",
            AuditStatus.NOT_FOUND,
            attempts=[_attempt("openalex", "not_found"), _attempt("crossref", "not_found")],
        ),
        _result(
            "D",
            AuditStatus.NOT_FOUND,
            attempts=[_attempt("openalex", "not_found"), _attempt("crossref", "not_found")],
        ),
    )
    return cases, response


def test_the_hand_worked_run_scores_as_worked_out(tmp_path):
    cases, response = _benchmark_set(tmp_path)
    report = score_response(cases, response)
    assert (report.total, report.passed, report.failed) == (4, 3, 1)
    assert report.status_accuracy == 0.75
    assert [score.case_id for score in report.scores if not score.passed] == ["C-recovered-venue"]
    assert report.actual_statuses == {"VERIFIED": 1, "METADATA_MISMATCH": 1, "NOT_FOUND": 2}


def test_the_hand_worked_per_state_figures(tmp_path):
    cases, response = _benchmark_set(tmp_path)
    per_state = score_response(cases, response).per_state
    assert per_state["VERIFIED"] == {
        "support": 1,
        "predicted": 1,
        "precision": 1.0,
        "recall": 1.0,
        "f1": 1.0,
    }
    assert per_state["METADATA_MISMATCH"]["support"] == 2
    assert per_state["METADATA_MISMATCH"]["predicted"] == 1
    assert per_state["METADATA_MISMATCH"]["recall"] == 0.5
    assert per_state["METADATA_MISMATCH"]["f1"] == pytest.approx(2 / 3)
    # C was expected to be a mismatch and answered NOT_FOUND, so that column
    # carries two predictions against one case: precision 1/2, recall 1/1.
    assert per_state["NOT_FOUND"] == {
        "support": 1,
        "predicted": 2,
        "precision": 0.5,
        "recall": 1.0,
        "f1": pytest.approx(2 / 3),
    }


def test_a_state_no_case_exercised_reports_no_metric_rather_than_zero(tmp_path):
    cases, response = _benchmark_set(tmp_path)
    report = score_response(cases, response)
    for state in ("NEEDS_REVIEW", "LOOKUP_FAILED"):
        assert report.per_state[state]["support"] == 0
        assert report.per_state[state]["precision"] is None
        assert report.per_state[state]["f1"] is None
    # Excluded from the macro average: three states had a figure, not five.
    assert report.macro_f1 == pytest.approx((1.0 + 2 / 3 + 2 / 3) / 3)


def test_the_hand_worked_confusion_matrix(tmp_path):
    cases, response = _benchmark_set(tmp_path)
    report = score_response(cases, response)
    assert report.confusion["VERIFIED"] == {"VERIFIED": 1}
    assert report.confusion["METADATA_MISMATCH"] == {"METADATA_MISMATCH": 1, "NOT_FOUND": 1}
    assert report.confusion["NOT_FOUND"] == {"NOT_FOUND": 1}
    assert report.confusion["NEEDS_REVIEW"] == {}


def test_the_hand_worked_field_accuracy(tmp_path):
    cases, response = _benchmark_set(tmp_path)
    report = score_response(cases, response)
    assert report.field_accuracy["year"] == {
        "checked": 3,
        "correct": 2,
        "accuracy": pytest.approx(2 / 3),
    }
    assert report.field_accuracy["title"]["accuracy"] == 1.0
    assert report.field_accuracy["doi"] == {"checked": 0, "correct": 0, "accuracy": None}
    # C pinned a year it never got, so the miss is visible as a transition.
    assert report.field_confusion["year"] == {
        "MATCH->MATCH": 1,
        "MISMATCH->MISMATCH": 1,
        "MISMATCH->ABSENT": 1,
    }


def test_the_hand_worked_run_holds_every_invariant(tmp_path):
    cases, response = _benchmark_set(tmp_path)
    safety = score_response(cases, response).safety
    assert safety.passed
    assert safety.total_results == 4
    assert safety.violations == []


# --- What a case refuses to accept ----------------------------------------------


def _one(tmp_path, payload, result):
    cases = _load(tmp_path, [payload])
    return score_response(cases, _response(result)).scores[0]


def test_a_status_the_case_did_not_expect_fails(tmp_path):
    score = _one(
        tmp_path,
        _case("x", {"status": "VERIFIED", "because": "fields_agree"}, bib_key="A"),
        _result("A", AuditStatus.NOT_FOUND, attempts=[_attempt("openalex", "not_found")]),
    )
    assert not score.passed
    assert "expected VERIFIED" in score.detail


def test_a_mechanism_that_did_not_fire_fails_even_when_the_status_matches(tmp_path):
    # The state is right, but nothing was recovered from the raw text: the case
    # and the fixture disagree about why, which is a broken pin, not a pass.
    score = _one(
        tmp_path,
        _case(
            "x",
            {"status": "METADATA_MISMATCH", "because": "field_differs_recovered"},
            bib_key="A",
        ),
        _result(
            "A",
            AuditStatus.METADATA_MISMATCH,
            matched_record=_record(),
            field_checks=[_check("venue", "MISMATCH")],
            attempts=[_attempt("openalex", "found")],
        ),
    )
    assert not score.passed
    assert "field_differs_recovered" in score.detail


def test_a_recovered_mismatch_satisfies_the_recovered_mechanism(tmp_path):
    score = _one(
        tmp_path,
        _case(
            "x",
            {"status": "METADATA_MISMATCH", "because": "field_differs_recovered"},
            bib_key="A",
        ),
        _result(
            "A",
            AuditStatus.METADATA_MISMATCH,
            matched_record=_record(),
            field_checks=[_check("venue", "MISMATCH", f"{RECOVERED_PREFIX}; venue from raw text.")],
            attempts=[_attempt("openalex", "found")],
        ),
    )
    assert score.passed, score.detail


def test_agreement_without_exactness_satisfies_its_own_mechanism(tmp_path):
    # Every required field agrees, the record was matched, and the state is
    # review: this is the exact gate withholding VERIFIED, which no other
    # mechanism names -- the field checks alone cannot tell it from a VERIFIED.
    score = _one(
        tmp_path,
        _case(
            "x",
            {"status": "NEEDS_REVIEW", "because": "fields_agree_not_exact"},
            bib_key="A",
        ),
        _result(
            "A",
            AuditStatus.NEEDS_REVIEW,
            matched_record=_record(),
            field_checks=[_check(name, "MATCH") for name in _REQUIRED],
            attempts=[_attempt("openalex", "found")],
        ),
    )
    assert score.passed, score.detail


def test_agreement_that_reached_verified_does_not_satisfy_the_review_mechanism(tmp_path):
    # The same checks and record, but the product called it VERIFIED. The case
    # says the exact gate should have withheld that, so it must fail: without
    # this, the mechanism would pass for a run whose gate never fired.
    score = _one(
        tmp_path,
        _case(
            "x",
            {"status": "VERIFIED", "because": "fields_agree_not_exact"},
            bib_key="A",
        ),
        _result(
            "A",
            AuditStatus.VERIFIED,
            matched_record=_record(),
            field_checks=[_check(name, "MATCH") for name in _REQUIRED],
            attempts=[_attempt("openalex", "found")],
        ),
    )
    assert not score.passed
    assert "fields_agree_not_exact" in score.detail


def test_review_with_no_matched_record_does_not_satisfy_the_agreement_mechanism(tmp_path):
    # A pre-lookup guard produces NEEDS_REVIEW with no record and no checks.
    # Agreeing with a record that was never found is not agreement.
    score = _one(
        tmp_path,
        _case(
            "x",
            {"status": "NEEDS_REVIEW", "because": "fields_agree_not_exact"},
            bib_key="A",
        ),
        _result("A", AuditStatus.NEEDS_REVIEW, reason="No searchable title was extracted."),
    )
    assert not score.passed
    assert "fields_agree_not_exact" in score.detail


def test_a_mismatch_on_the_wrong_field_fails(tmp_path):
    score = _one(
        tmp_path,
        _case(
            "x",
            {
                "status": "METADATA_MISMATCH",
                "because": "field_differs_stated",
                "field_checks": {"year": "MISMATCH"},
            },
            bib_key="A",
        ),
        _result(
            "A",
            AuditStatus.METADATA_MISMATCH,
            matched_record=_record(),
            field_checks=[_check("venue", "MISMATCH")],
            attempts=[_attempt("openalex", "found")],
        ),
    )
    assert not score.passed
    assert "field year ABSENT, expected MISMATCH" in score.detail


def test_a_field_check_the_case_expected_and_never_got_is_a_miss(tmp_path):
    score = _one(
        tmp_path,
        _case(
            "x",
            {
                "status": "NOT_FOUND",
                "because": "no_acceptable_record",
                "field_checks": {"title": "MATCH"},
            },
            bib_key="A",
        ),
        _result("A", AuditStatus.NOT_FOUND, attempts=[_attempt("openalex", "not_found")]),
    )
    assert not score.passed
    assert "field title ABSENT" in score.detail


def test_selecting_a_forbidden_record_fails(tmp_path):
    score = _one(
        tmp_path,
        _case(
            "x",
            {
                "status": "METADATA_MISMATCH",
                "because": "field_differs_stated",
                "forbidden_record_ids": ["W-wrong"],
            },
            bib_key="A",
        ),
        _result(
            "A",
            AuditStatus.METADATA_MISMATCH,
            matched_record=_record(record_id="W-wrong"),
            field_checks=[_check("year", "MISMATCH")],
            attempts=[_attempt("openalex", "found")],
        ),
    )
    assert not score.passed
    assert "forbidden record W-wrong" in score.detail


def test_the_wrong_provider_is_reported(tmp_path):
    score = _one(
        tmp_path,
        _case(
            "x",
            {"status": "VERIFIED", "because": "fields_agree", "matched_provider": "crossref"},
            bib_key="A",
        ),
        _result(
            "A",
            AuditStatus.VERIFIED,
            matched_record=_record(provider="openalex"),
            field_checks=[_check(name, "MATCH") for name in _REQUIRED],
            attempts=[_attempt("openalex", "found")],
        ),
    )
    assert not score.passed
    assert "matched provider 'openalex'" in score.detail


def test_a_different_attempt_sequence_fails(tmp_path):
    score = _one(
        tmp_path,
        _case(
            "x",
            {
                "status": "NOT_FOUND",
                "because": "no_acceptable_record",
                "lookup_attempts": ["openalex:not_found", "crossref:not_found"],
            },
            bib_key="A",
        ),
        _result("A", AuditStatus.NOT_FOUND, attempts=[_attempt("openalex", "not_found")]),
    )
    assert not score.passed
    assert "attempts ['openalex:not_found']" in score.detail


def test_an_attempt_error_code_the_case_pins_is_checked(tmp_path):
    # A transport failure and a throttle are both "failed" on the wire. Only the
    # code separates them, so a case that pins the code is checking something the
    # outcome cannot say.
    score = _one(
        tmp_path,
        _case(
            "x",
            {
                "status": "LOOKUP_FAILED",
                "because": "provider_failed",
                "attempt_errors": {"openalex": "OPENALEX_TRANSPORT"},
            },
            bib_key="A",
        ),
        _result(
            "A",
            AuditStatus.LOOKUP_FAILED,
            attempts=[_attempt("openalex", "failed", error_code="OPENALEX_TRANSPORT")],
        ),
    )
    assert score.passed, score.detail


def test_the_wrong_attempt_error_code_fails(tmp_path):
    score = _one(
        tmp_path,
        _case(
            "x",
            {
                "status": "LOOKUP_FAILED",
                "because": "provider_failed",
                "attempt_errors": {"openalex": "OPENALEX_TRANSPORT"},
            },
            bib_key="A",
        ),
        _result(
            "A",
            AuditStatus.LOOKUP_FAILED,
            attempts=[_attempt("openalex", "failed", error_code="OPENALEX_RATE_LIMITED")],
        ),
    )
    assert not score.passed
    assert "OPENALEX_TRANSPORT" in score.detail


def test_an_attempt_error_for_a_provider_that_never_ran_fails(tmp_path):
    score = _one(
        tmp_path,
        _case(
            "x",
            {
                "status": "LOOKUP_FAILED",
                "because": "provider_failed",
                "attempt_errors": {"crossref": "CROSSREF_HTTP_500"},
            },
            bib_key="A",
        ),
        _result(
            "A",
            AuditStatus.LOOKUP_FAILED,
            attempts=[_attempt("openalex", "failed", error_code="OPENALEX_HTTP_500")],
        ),
    )
    assert not score.passed
    assert "ABSENT" in score.detail


def test_an_attempt_detail_the_case_quotes_is_checked(tmp_path):
    # Two routes to the same state leave the same "openalex:found" behind: the
    # identifier pre-pass and the exact-title search. A case that means to
    # exercise one of them has to pin the rule, or it passes on the other.
    score = _one(
        tmp_path,
        _case(
            "x",
            {
                "status": "VERIFIED",
                "because": "fields_agree",
                "attempt_details": {"openalex": "doi identifies this record exactly"},
            },
            bib_key="A",
        ),
        _result(
            "A",
            AuditStatus.VERIFIED,
            field_checks=[_check(name, "MATCH") for name in ("title", "authors", "year", "venue")],
            matched_record=_record(),
            attempts=[
                _attempt(
                    "openalex", "found", detail="the reference's doi identifies this record exactly"
                )
            ],
        ),
    )
    assert score.passed, score.detail


def test_an_attempt_detail_from_the_other_route_fails(tmp_path):
    # The same status, the same single found attempt, and the wrong rule: the
    # case asked for the identifier pre-pass and got the title search.
    score = _one(
        tmp_path,
        _case(
            "x",
            {
                "status": "VERIFIED",
                "because": "fields_agree",
                "attempt_details": {"openalex": "doi identifies this record exactly"},
            },
            bib_key="A",
        ),
        _result(
            "A",
            AuditStatus.VERIFIED,
            field_checks=[_check(name, "MATCH") for name in ("title", "authors", "year", "venue")],
            matched_record=_record(),
            attempts=[_attempt("openalex", "found", detail="the title matches exactly")],
        ),
    )
    assert not score.passed
    assert "does not contain" in score.detail


def test_an_attempt_detail_for_a_provider_that_never_ran_fails(tmp_path):
    score = _one(
        tmp_path,
        _case(
            "x",
            {
                "status": "NOT_FOUND",
                "because": "no_acceptable_record",
                "attempt_details": {"crossref": "title matches exactly"},
            },
            bib_key="A",
        ),
        _result(
            "A",
            AuditStatus.NOT_FOUND,
            attempts=[_attempt("openalex", "not_found", detail="no record matches")],
        ),
    )
    assert not score.passed
    assert "ABSENT" in score.detail


def test_a_reason_the_case_quotes_is_checked(tmp_path):
    score = _one(
        tmp_path,
        _case(
            "x",
            {
                "status": "NEEDS_REVIEW",
                "because": "no_searchable_title",
                "reason_contains": "No searchable title",
            },
            bib_key="A",
        ),
        _result("A", AuditStatus.NEEDS_REVIEW, reason="Something else happened."),
    )
    assert not score.passed
    assert "No searchable title" in score.detail


def test_candidates_must_be_present_when_the_case_says_so(tmp_path):
    score = _one(
        tmp_path,
        _case(
            "x",
            {"status": "NEEDS_REVIEW", "because": "ambiguous_records", "candidates_required": True},
            bib_key="A",
        ),
        _result("A", AuditStatus.NEEDS_REVIEW, attempts=[_attempt("openalex", "ambiguous")]),
    )
    assert not score.passed
    assert "no candidate records" in score.detail


def test_an_ambiguous_lookup_with_candidates_satisfies_the_mechanism(tmp_path):
    score = _one(
        tmp_path,
        _case(
            "x",
            {"status": "NEEDS_REVIEW", "because": "ambiguous_records", "candidates_required": True},
            bib_key="A",
        ),
        _result(
            "A",
            AuditStatus.NEEDS_REVIEW,
            candidates=[_record(record_id="W1"), _record(record_id="W2")],
            attempts=[_attempt("openalex", "ambiguous")],
        ),
    )
    assert score.passed, score.detail


def test_the_pre_lookup_guard_is_its_own_mechanism(tmp_path):
    source = _case(
        "x",
        {
            "status": "NEEDS_REVIEW",
            "because": "no_searchable_title",
            "reason_contains": "No searchable title",
        },
        bib_key="A",
    )
    okay = _one(
        tmp_path,
        source,
        _result(
            "A",
            AuditStatus.NEEDS_REVIEW,
            reason="No searchable title was extracted from the reference.",
        ),
    )
    assert okay.passed, okay.detail
    # Same status, same absence of attempts, but a provider was never skipped:
    # the reason is what separates the guard from a lookup that ran and failed.
    wrong = _one(
        tmp_path,
        source,
        _result("A", AuditStatus.NEEDS_REVIEW, reason="Two candidates looked equally good."),
    )
    assert not wrong.passed
    assert "no_searchable_title" in wrong.detail


# --- Joining --------------------------------------------------------------------


def test_an_unmatched_case_scores_as_no_result(tmp_path):
    cases = _load(
        tmp_path,
        [_case("x", {"status": "VERIFIED", "because": "fields_agree"}, bib_key="missing")],
    )
    score = score_response(cases, _response(_result("A", AuditStatus.VERIFIED))).scores[0]
    assert score.actual_status == UNMATCHED
    assert not score.passed
    assert "no result in the response matches" in score.detail


def test_a_case_may_join_by_raw_text(tmp_path):
    cases = _load(
        tmp_path,
        [
            _case(
                "x",
                {"status": "NEEDS_REVIEW", "because": "no_searchable_title"},
                raw_text_contains="Proceedings of the 2019 Conference",
            )
        ],
    )
    response = _response(
        _result("A", AuditStatus.NOT_FOUND, attempts=[_attempt("openalex", "not_found")]),
        _result(
            "7",
            AuditStatus.NEEDS_REVIEW,
            reason="No searchable title",
            raw_text="[7] Proceedings of the 2019 Conference on Empirical Methods.",
        ),
    )
    assert score_response(cases, response).scores[0].passed


def test_a_case_may_join_by_position(tmp_path):
    payload = _case("x", {"status": "NOT_FOUND", "because": "no_acceptable_record"}, index=1)
    cases = _load(tmp_path, [payload])
    response = _response(
        _result("A", AuditStatus.VERIFIED),
        _result("B", AuditStatus.NOT_FOUND, attempts=[_attempt("openalex", "not_found")]),
    )
    assert score_response(cases, response).scores[0].passed


def test_two_cases_never_claim_the_same_result(tmp_path):
    cases = _load(
        tmp_path,
        [
            _case(
                "first",
                {"status": "NOT_FOUND", "because": "no_acceptable_record"},
                bib_key="A",
            ),
            _case(
                "second",
                {"status": "NOT_FOUND", "because": "no_acceptable_record"},
                bib_key="A",
            ),
        ],
    )
    response = _response(
        _result("A", AuditStatus.NOT_FOUND, attempts=[_attempt("openalex", "not_found")])
    )
    report = score_response(cases, response)
    assert [score.actual_status for score in report.scores] == ["NOT_FOUND", UNMATCHED]


def test_the_unmatched_column_appears_only_when_something_is_unmatched(tmp_path):
    cases = _load(
        tmp_path,
        [_case("x", {"status": "NOT_FOUND", "because": "no_acceptable_record"}, bib_key="missing")],
    )
    report = score_response(cases, _response(_result("A", AuditStatus.NOT_FOUND)))
    rendered = render_report(report, title="t", source="s")
    assert UNMATCHED[:12] in rendered
    assert "0.0%" in rendered


# --- Safety invariants ----------------------------------------------------------


def test_a_completed_search_reporting_not_found_holds(tmp_path):
    report = check_safety(
        [_result("A", AuditStatus.NOT_FOUND, attempts=[_attempt("openalex", "not_found")])]
    )
    assert report.passed


def test_not_found_after_a_failed_provider_is_a_violation():
    report = check_safety(
        [
            _result(
                "A",
                AuditStatus.NOT_FOUND,
                attempts=[
                    _attempt("openalex", "not_found"),
                    _attempt("crossref", "failed", "TRANSPORT"),
                ],
            )
        ]
    )
    assert not report.passed
    assert report.not_found_with_incomplete_search == ["entry-A"]


def test_not_found_with_no_attempt_at_all_is_a_violation():
    report = check_safety([_result("A", AuditStatus.NOT_FOUND)])
    assert report.not_found_with_incomplete_search == ["entry-A"]
    assert report.skipped_lookup_without_review == ["entry-A"]


def test_not_found_carrying_field_checks_is_a_violation():
    report = check_safety(
        [
            _result(
                "A",
                AuditStatus.NOT_FOUND,
                field_checks=[_check("title", "MISMATCH")],
                attempts=[_attempt("openalex", "not_found")],
            )
        ]
    )
    assert report.not_found_with_field_checks == ["entry-A"]


def test_lookup_failed_without_a_failure_is_a_violation():
    report = check_safety(
        [_result("A", AuditStatus.LOOKUP_FAILED, attempts=[_attempt("openalex", "not_found")])]
    )
    assert report.lookup_failed_without_a_failure == ["entry-A"]


def test_lookup_failed_after_a_provider_failed_holds():
    report = check_safety(
        [
            _result(
                "A",
                AuditStatus.LOOKUP_FAILED,
                attempts=[_attempt("openalex", "failed", "RATE_LIMITED")],
            )
        ]
    )
    assert report.passed


def test_skipping_the_lookup_without_review_is_a_violation():
    report = check_safety([_result("A", AuditStatus.VERIFIED, matched_record=_record())])
    assert report.skipped_lookup_without_review == ["entry-A"]


def test_the_pre_lookup_guard_holds_with_no_attempts():
    report = check_safety(
        [_result("A", AuditStatus.NEEDS_REVIEW, reason="No searchable title was extracted.")]
    )
    assert report.passed


def test_verified_without_a_record_is_a_violation():
    report = check_safety(
        [
            _result(
                "A",
                AuditStatus.VERIFIED,
                field_checks=[_check(name, "MATCH") for name in _REQUIRED],
                attempts=[_attempt("openalex", "found")],
            )
        ]
    )
    assert report.verified_without_a_record == ["entry-A"]


def test_verified_with_a_required_field_unchecked_is_a_violation():
    report = check_safety(
        [
            _result(
                "A",
                AuditStatus.VERIFIED,
                matched_record=_record(),
                field_checks=[_check("title", "MATCH"), _check("venue", "NOT_CHECKED")],
                attempts=[_attempt("openalex", "found")],
            )
        ]
    )
    assert report.verified_without_a_record == ["entry-A"]


def test_the_violations_are_listed_together():
    report = check_safety(
        [
            _result("A", AuditStatus.NOT_FOUND),
            _result("B", AuditStatus.LOOKUP_FAILED, attempts=[_attempt("openalex", "not_found")]),
        ]
    )
    assert len(report.violations) == 3
    assert report.total_results == 2


# --- Loading --------------------------------------------------------------------


def test_an_unknown_status_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="MAYBE"):
        _load(tmp_path, [_case("x", {"status": "MAYBE", "because": "fields_agree"}, bib_key="A")])


def test_an_unknown_mechanism_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="vibes"):
        _load(tmp_path, [_case("x", {"status": "VERIFIED", "because": "vibes"}, bib_key="A")])


def test_a_case_with_no_mechanism_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="mechanism"):
        _load(tmp_path, [_case("x", {"status": "VERIFIED"}, bib_key="A")])


def test_an_unknown_field_name_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="publisher"):
        _load(
            tmp_path,
            [
                _case(
                    "x",
                    {
                        "status": "VERIFIED",
                        "because": "fields_agree",
                        "field_checks": {"publisher": "MATCH"},
                    },
                    bib_key="A",
                )
            ],
        )


def test_an_unknown_field_status_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="ALMOST"):
        _load(
            tmp_path,
            [
                _case(
                    "x",
                    {
                        "status": "VERIFIED",
                        "because": "fields_agree",
                        "field_checks": {"year": "ALMOST"},
                    },
                    bib_key="A",
                )
            ],
        )


def test_a_case_with_no_join_key_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="exactly one of"):
        _load(tmp_path, [_case("x", {"status": "VERIFIED", "because": "fields_agree"})])


def test_a_case_with_two_join_keys_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="exactly one of"):
        _load(
            tmp_path,
            [_case("x", {"status": "VERIFIED", "because": "fields_agree"}, bib_key="A", index=0)],
        )


def test_a_case_with_no_id_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="case_id"):
        _load(
            tmp_path,
            [{"expected": {"status": "VERIFIED", "because": "fields_agree"}, "bib_key": "A"}],
        )


def test_a_non_list_case_file_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="list of cases"):
        _load(tmp_path, {"cases": "everything"})


def test_a_wrapped_case_list_is_accepted(tmp_path):
    path = tmp_path / "cases.json"
    cases = [_case("x", {"status": "VERIFIED", "because": "fields_agree"}, bib_key="A")]
    path.write_text(json.dumps({"cases": cases}), encoding="utf-8")
    assert len(load_cases(path)) == 1


def test_an_empty_case_file_is_a_valid_target(tmp_path):
    path = tmp_path / "cases.json"
    path.write_text("[]", encoding="utf-8")
    assert load_cases(path) == []


# --- Rendering ------------------------------------------------------------------


def test_the_report_names_the_failing_case_and_its_reason(tmp_path):
    cases, response = _benchmark_set(tmp_path)
    rendered = render_report(score_response(cases, response), title="audit", source="replay")
    assert "== audit ==" in rendered
    assert "cases        : 4  passed 3  failed 1" in rendered
    assert "accuracy     : 75.0%  (status, exact match)" in rendered
    assert "macro F1     : 77.8%" in rendered
    assert "C-recovered-venue: status NOT_FOUND, expected METADATA_MISMATCH" in rendered
    assert "safety       : all invariants hold over 4 result(s)" in rendered


def test_the_report_prints_the_confusion_matrix_by_row(tmp_path):
    cases = _load(
        tmp_path,
        [
            _case(
                "x",
                {
                    "status": "VERIFIED",
                    "because": "fields_agree",
                    "field_checks": {name: "MATCH" for name in _REQUIRED},
                },
                bib_key="A",
            )
        ],
    )
    response = _response(
        _result(
            "A",
            AuditStatus.VERIFIED,
            matched_record=_record(),
            field_checks=[_check(name, "MATCH") for name in _REQUIRED],
            attempts=[_attempt("openalex", "found")],
        )
    )
    rendered = render_report(score_response(cases, response), title="t", source="s")
    assert "confusion (row expected, column reported):" in rendered
    assert "VERIFIED" in rendered
    assert "  title        1/1      100.0%  MATCH->MATCH=1" in rendered


def test_the_report_says_which_fields_are_not_checked_by_any_case(tmp_path):
    cases, response = _benchmark_set(tmp_path)
    rendered = render_report(score_response(cases, response), title="t", source="s")
    # doi is pinned by no case, so it must not appear with a fabricated figure.
    assert "doi" not in rendered


def test_a_run_that_scored_nothing_reports_no_metric(tmp_path):
    empty = score_response([], _response())
    rendered = render_report(empty, title="t", source="s")
    assert "accuracy     : n/a" in rendered
    assert "statuses     : none" in rendered
    assert "safety       : all invariants hold over 0 result(s)" in rendered


def test_a_violation_is_named_in_the_report(tmp_path):
    cases = _load(
        tmp_path,
        [_case("x", {"status": "NOT_FOUND", "because": "no_acceptable_record"}, bib_key="A")],
    )
    report = score_response(cases, _response(_result("A", AuditStatus.NOT_FOUND)))
    rendered = render_report(report, title="t", source="s")
    assert "safety       : VIOLATED over 1 result(s)" in rendered
    assert "NOT_FOUND after an incomplete search: entry-A" in rendered


def test_the_payload_is_json_serialisable(tmp_path):
    cases, response = _benchmark_set(tmp_path)
    payload = report_payload(score_response(cases, response))
    assert payload["status_accuracy"] == 0.75
    assert payload["safety"]["passed"] is True
    assert len(payload["scores"]) == 4
    round_tripped = json.loads(json.dumps(payload))
    assert round_tripped["per_state"]["NOT_FOUND"]["precision"] == 0.5
    assert round_tripped["per_state"]["NEEDS_REVIEW"]["f1"] is None


# --- The recorded answers -------------------------------------------------------
#
# audit_benchmark.py's own machinery. It has to be tested here rather than only
# by the replay, because the failures it had were failures to notice: a slug
# that dropped the word distinguishing two queries let one recorded answer
# replace another, and a recording of 429 bodies looked exactly like a
# recording of results.


def _provider_body(records):
    return {"results": records}


def _work(record_id, title, year=2001):
    return {
        "id": f"https://openalex.org/{record_id}",
        "doi": "",
        "title": title,
        "publication_year": year,
        "authorships": [],
        "primary_location": {"source": {"display_name": "A Venue", "type": "journal"}},
        "type": "article",
    }


def _pin(url, provider="openalex", status_code=200, body=None, error="", **kwargs):
    from backend.scripts.audit_benchmark import Pin

    return Pin(
        url=url,
        provider=provider,
        source=kwargs.pop("source", "captured"),
        status_code=status_code,
        body=body if body is not None else _provider_body([_work("W1", "A Title")]),
        error=error,
        **kwargs,
    )


def test_two_queries_differing_only_in_the_author_get_different_names(tmp_path):
    """The truncation dropped the surname, which is the only differing word."""
    from backend.scripts.audit_benchmark import _capture_path

    base = "https://api.openalex.org/works?filter=title.search%3A{}&per-page=10"
    title = "Batch+Normalization%3A+Accelerating+Deep+Network+Training+by+Reducing+Shift"
    first = _pin(base.format(title + "+ioffe"))
    second = _pin(base.format(title + "+szegedy"))
    assert _capture_path(tmp_path, first) != _capture_path(tmp_path, second)


def test_a_capture_the_network_failed_is_not_stored(tmp_path):
    from backend.scripts.audit_benchmark import load_pins, save_captures

    url = "https://api.openalex.org/works?filter=title.search%3AThrottled&per-page=10"
    failed, drifted, written, unchanged = save_captures(
        tmp_path,
        {url: _pin(url, status_code=429, body=None, error="HTTP 429 Too Many Requests")},
        {},
        accept=False,
    )
    assert failed == [url]
    assert (drifted, written, unchanged) == ([], 0, 0)
    assert load_pins(tmp_path) == {}


def test_a_failed_recording_does_not_replace_a_good_capture(tmp_path):
    from backend.scripts.audit_benchmark import load_pins, save_captures

    url = "https://api.openalex.org/works?filter=title.search%3AKnown&per-page=10"
    good = _pin(url)
    save_captures(tmp_path, {url: good}, {}, accept=False)
    before = load_pins(tmp_path)[url].body

    failed, drifted, written, _ = save_captures(
        tmp_path,
        {url: _pin(url, status_code=429, body=None, error="HTTP 429 Too Many Requests")},
        load_pins(tmp_path),
        accept=True,
    )
    assert failed == [url]
    assert (drifted, written) == ([], 0)
    assert load_pins(tmp_path)[url].body == before


def test_a_record_appearing_in_an_answer_reads_as_drift(tmp_path):
    from backend.scripts.audit_benchmark import load_pins, save_captures

    url = "https://api.openalex.org/works?filter=title.search%3AMoving&per-page=10"
    save_captures(tmp_path, {url: _pin(url)}, {}, accept=False)
    existing = load_pins(tmp_path)
    grown = _pin(url, body=_provider_body([_work("W1", "A Title"), _work("W2", "Another")]))
    drifted, written, _ = save_captures(tmp_path, {url: grown}, existing, accept=False)[1:]
    assert drifted == [url]
    assert written == 0


def test_reordering_the_same_records_is_not_drift(tmp_path):
    """Crossref reorders records it scores equally; no case depends on it."""
    from backend.scripts.audit_benchmark import load_pins, save_captures

    url = "https://api.crossref.org/works?query.bibliographic=Moving&rows=10"
    first, second = _work("W1", "A Title"), _work("W2", "Another")
    save_captures(
        tmp_path,
        {url: _pin(url, "crossref", body=_provider_body([first, second]))},
        {},
        accept=False,
    )
    reordered = _pin(url, "crossref", body=_provider_body([second, first]))
    drifted, written, unchanged = save_captures(
        tmp_path, {url: reordered}, load_pins(tmp_path), accept=False
    )[1:]
    assert (drifted, written, unchanged) == ([], 0, 1)


def test_an_injected_pin_is_never_recorded_over(tmp_path):
    """Injection is a hand edit, so it is a file written here rather than a capture.

    It also shows why injection cannot go through save_captures: an injected pin
    is a failure, and a failure is exactly what recording refuses to store. A
    person writes the file; recording only ever reads it.
    """
    from backend.scripts.audit_benchmark import load_pins, save_captures

    url = "https://api.openalex.org/works?filter=title.search%3AForced&per-page=10"
    (tmp_path / "injected.json").write_text(
        json.dumps(
            {
                "url": url,
                "provider": "openalex",
                "source": "injected",
                "status_code": 500,
                "error": "HTTP 500 Server Error",
                "body": None,
                "note": "Forced for the failure case.",
            }
        ),
        encoding="utf-8",
    )
    live = _pin(url)
    failed, drifted, written, unchanged = save_captures(
        tmp_path, {url: live}, load_pins(tmp_path), accept=True
    )
    assert (failed, drifted, written, unchanged) == ([], [], 0, 0)
    assert load_pins(tmp_path)[url].status_code == 500


def test_two_answers_that_want_one_file_are_refused(tmp_path, monkeypatch):
    """One file cannot hold both, and the second write would be silent."""
    from backend.scripts import audit_benchmark

    urls = [
        "https://api.openalex.org/works?filter=title.search%3AOne&per-page=10",
        "https://api.openalex.org/works?filter=title.search%3ATwo&per-page=10",
    ]
    same = lambda directory, pin: directory / "same.json"  # noqa: E731
    monkeypatch.setattr(audit_benchmark, "_capture_path", same)
    with pytest.raises(RuntimeError, match="would answer two different requests"):
        audit_benchmark.save_captures(tmp_path, {url: _pin(url) for url in urls}, {}, accept=False)


# --- Timing ---------------------------------------------------------------------


def test_every_document_size_measures_a_document_that_size():
    """The shares round independently, so a size the mix cannot divide exactly
    still has to come out the length it was asked for. A document that quietly
    came up short would still produce a plausible curve."""
    from backend.scripts import audit_benchmark

    for size in (*range(1, 18), 30, 81, 200):
        slots = audit_benchmark.timing_slots(size)
        assert len(slots) == size, size
        assert set(slots) <= set(audit_benchmark.SHAPES), size


def test_a_document_costs_the_requests_its_shapes_cost():
    from backend.scripts import audit_benchmark

    slots = audit_benchmark.timing_slots(80)
    requests, states = audit_benchmark.timing_document(80)
    assert requests == sum(audit_benchmark.SHAPES[case_id][0] for case_id in slots)
    assert requests == 120
    assert states == {"VERIFIED": 40, "NOT_FOUND": 24, "LOOKUP_FAILED": 16}
    # The two shapes that need both providers are the ones that make the curve
    # steeper than the entry count: 120 requests for 80 entries.
    assert requests > 80


def test_the_timing_document_renames_keys_and_leaves_the_query_alone():
    """The provider query comes from the title and the first author's surname,
    which is what lets a hundred copies share one recorded answer. The new key
    must not reach the title, or every copy would ask for an unfixtured URL."""
    from backend.scripts import audit_benchmark

    cases = audit_benchmark.load_benchmark_cases(audit_benchmark.CASE_FILE)
    by_id = {case.case_id: case for case in cases}
    built = audit_benchmark.timing_cases(cases, 5)

    assert len({case.case_id for case in built}) == 5
    for index, case in enumerate(built):
        shape = by_id[audit_benchmark.timing_slots(5)[index]]
        assert case.case_id == f"timing-5-{index:03d}"
        assert case.scored.case_id == case.case_id
        assert case.scored.bib_key == case.case_id
        # Byte-identical from the title onwards: the renamed key is the only
        # difference, and the key is not part of the query.
        assert case.bib_source.split("\n", 1)[1] == shape.bib_source.split("\n", 1)[1]
        # And the shape's own key is gone from the document.
        assert f"{{{shape.case_id}," not in case.bib_source


def test_a_shape_the_case_file_does_not_hold_is_refused():
    from backend.scripts import audit_benchmark

    cases = audit_benchmark.load_benchmark_cases(audit_benchmark.CASE_FILE)
    kept = [case for case in cases if case.case_id != "provider-500"]
    with pytest.raises(ValueError, match="does not hold the timing shapes"):
        audit_benchmark.timing_cases(kept, 5)


def _curve(*medians):
    """A measured curve from medians, with the request counts the mix implies."""
    sizes = (5, 10, 20, 40, 80)
    requests = (8, 15, 30, 60, 120)
    return [
        {"size": size, "requests": count, "median": median}
        for size, count, median in zip(sizes, requests, medians)
    ]


def test_a_serial_curve_passes_the_slope_band():
    from backend.scripts import audit_benchmark

    # 0.055s per request over 0.05s of injected latency: the chain waited for
    # each request, so the extra requests cost about one latency each.
    slopes, problems = audit_benchmark.scaling_problems(
        _curve(0.45, 0.85, 1.70, 3.35, 6.65), latency=0.05
    )
    assert problems == [], problems
    assert [row["sizes"] for row in slopes] == [[5, 10], [10, 20], [20, 40], [40, 80]]


def test_a_flattened_curve_fails_the_slope_band():
    """What a concurrent chain looks like: ten times the requests, no more wall
    clock. This is the reading the tier exists to catch."""
    from backend.scripts import audit_benchmark

    _, problems = audit_benchmark.scaling_problems(
        _curve(0.40, 0.42, 0.45, 0.48, 0.52), latency=0.05
    )
    assert len(problems) == 4
    assert "outside the" in problems[0]
    assert "0.05s each pinned request was told to take" in problems[0]


def test_a_constant_offset_does_not_move_the_slope():
    """Differencing is why: the passing curve from the test above with a second
    added to every row is the same machine doing the same work behind a slower
    one, and it must read as the same chain."""
    from backend.scripts import audit_benchmark

    slopes, problems = audit_benchmark.scaling_problems(
        _curve(1.45, 1.85, 2.70, 4.35, 7.65), latency=0.05
    )
    assert problems == [], problems
    assert [row["seconds_per_request"] for row in slopes] == [0.0571, 0.0567, 0.055, 0.055]
