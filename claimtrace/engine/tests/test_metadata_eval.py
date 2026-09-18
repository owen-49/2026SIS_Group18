"""Tests for metadata_eval.py.

This module is what turns "the thresholds were measured" into something a
reviewer can check, so the tests are mostly about the ways a measurement can
lie: an unannotated case scored as correct, a wrong record scored as right
because the status happened to match, a sweep that reports a number without
saying which case moved.

The sweep tests run the sweep over ``YEAR_TOLERANCE`` against the real
reference that constant is pinned by, so the case that moves is the case the
annotation was written from. They assert a flip in each direction, because a
constant pinned from one side only is a constant nobody has measured.
"""

import json
from unittest.mock import patch

import pytest

from engine import identity
from engine.identity import PublicationCandidate, ReferenceQuery
from engine.metadata_eval import (
    CaseScore,
    EvalCase,
    ExpectedIdentity,
    candidate_from_dict,
    candidate_to_dict,
    candidates_for,
    load_cases,
    load_recordings,
    query_for,
    save_recording,
    score_all,
    score_case,
    summarize,
    sweep_threshold,
    sweep_values,
)

_TPAMI = "IEEE Transactions on Pattern Analysis and Machine Intelligence"
_CVPR = "IEEE Conference on Computer Vision and Pattern Recognition"
_NEURIPS = "Advances in Neural Information Processing Systems"
_TPAMI_DOI = "10.1109/TPAMI.2014.2361319"

# backend/uploads/parsed/f940bcbf-...references.json #1, verbatim.
_INVERTED_TEXT = (
    "[1] Artem Babenko and Victor Lempitsky. The inverted multi-index. "
    "IEEE Transactions on Pattern Analysis and Machine Intelligence, 2014."
)


def _query(**overrides):
    fields = {
        "title": "The inverted multi-index",
        "authors": ["Artem Babenko", "Victor Lempitsky"],
        "year": 2014,
        "venue": _TPAMI,
    }
    fields.update(overrides)
    return ReferenceQuery(**fields)


def _candidate(**overrides):
    fields = {
        "provider": "crossref",
        "record_id": _TPAMI_DOI,
        "title": "The inverted multi-index",
        "authors": ["Artem Babenko", "Victor Lempitsky"],
        "year": 2014,
        "venue": _TPAMI,
        "kind": "article",
        "doi": _TPAMI_DOI,
    }
    fields.update(overrides)
    return PublicationCandidate(**fields)


def _case(expected, *, query=None, raw_text="", case_id="f940bcbf-1"):
    return EvalCase(
        case_id=case_id,
        source_file="f940bcbf.references.json",
        source_number=1,
        raw_text=raw_text,
        query=query or _query(),
        expected=expected,
    )


def _score(case_id, passed, *, status="found", rule="exact-title", selected="10.1/x", detail=""):
    return CaseScore(
        case_id=case_id,
        passed=passed,
        expected_status="found",
        actual_status=status,
        rule=rule,
        selected_id=selected,
        detail=detail,
    )


# --- Loading the annotated set -------------------------------------------------


def _write(tmp_path, payload):
    path = tmp_path / "fixture.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


_CASE_PAYLOAD = {
    "case_id": "f940bcbf-1",
    "source_file": "f940bcbf.references.json",
    "source_number": 1,
    "raw_text": _INVERTED_TEXT,
    "query": {"title": "The inverted multi-index", "year": 2014, "venue": _TPAMI},
    "expected": {
        "status": "found",
        "acceptable_dois": [_TPAMI_DOI],
        "forbidden_dois": ["10.1109/CVPR.2012.6248012"],
        "notes": "the TPAMI article, not the CVPR version",
    },
}


def test_load_cases_reads_the_query_and_the_expectation(tmp_path):
    cases = load_cases(_write(tmp_path, {"cases": [_CASE_PAYLOAD]}))
    assert len(cases) == 1
    case = cases[0]
    assert case.case_id == "f940bcbf-1"
    assert case.source_file == "f940bcbf.references.json"
    assert case.source_number == 1
    assert case.query.title == "The inverted multi-index"
    assert case.query.year == 2014
    assert case.expected.status == "found"
    assert case.expected.acceptable_dois == [_TPAMI_DOI]
    assert case.expected.forbidden_dois == ["10.1109/CVPR.2012.6248012"]
    assert case.expected.notes == "the TPAMI article, not the CVPR version"


def test_load_cases_accepts_a_bare_list(tmp_path):
    assert len(load_cases(_write(tmp_path, [_CASE_PAYLOAD]))) == 1


def test_load_cases_defaults_the_optional_expectation_fields(tmp_path):
    payload = {**_CASE_PAYLOAD, "expected": {"status": "not_found"}}
    expected = load_cases(_write(tmp_path, [payload]))[0].expected
    assert expected.acceptable_dois == []
    assert expected.forbidden_dois == []
    assert expected.forbidden_doi_prefixes == []
    assert expected.notes == ""


def test_a_malformed_case_is_rejected_rather_than_skipped(tmp_path):
    for broken in [
        {"source_number": 1},  # no case_id
        {"case_id": "x", "query": {}},  # no expected block
        "not-a-case",
        {**_CASE_PAYLOAD, "query": "not-a-dict"},
        {**_CASE_PAYLOAD, "expected": []},
    ]:
        with pytest.raises(ValueError):
            load_cases(_write(tmp_path, [broken]))


def test_a_fixture_that_is_not_a_list_is_rejected(tmp_path):
    with pytest.raises(ValueError):
        load_cases(_write(tmp_path, {"cases": "nope"}))


def test_loading_a_missing_fixture_raises_rather_than_returning_nothing(tmp_path):
    # The one deviation from "public functions never raise" in this package, and
    # it is deliberate: an empty case set scores 100% on every sweep, so a
    # loader that swallowed a bad path would report a broken fixture as a clean
    # measurement. Failing loudly is the only safe direction here.
    with pytest.raises(OSError):
        load_cases(tmp_path / "absent.json")


# --- Which query a case is scored with -----------------------------------------


def test_the_documented_query_sources_are_the_two_that_exist():
    case = _case(ExpectedIdentity(status="found"), raw_text=_INVERTED_TEXT)
    assert query_for(case, "fixture").title == "The inverted multi-index"
    assert query_for(case, "parsed").title == "The inverted multi-index"
    with pytest.raises(ValueError):
        query_for(case, "guessed")


def test_the_parsed_query_comes_from_the_raw_text_not_the_fixture_block():
    # Scoring the fixture's own query separates a mistake in the identity rule
    # from a mistake in reference parsing; this is the switch that separates them.
    case = _case(
        ExpectedIdentity(status="found", acceptable_dois=[_TPAMI_DOI]),
        query=_query(title="an unrelated title"),
        raw_text=_INVERTED_TEXT,
    )
    assert query_for(case, "parsed").title == "The inverted multi-index"
    assert query_for(case, "parsed").venue == _TPAMI


def test_the_query_source_changes_the_score():
    recordings = {"f940bcbf-1": [_candidate()]}
    cases = [
        _case(
            ExpectedIdentity(status="found", acceptable_dois=[_TPAMI_DOI]),
            query=_query(title="an unrelated title"),
            raw_text=_INVERTED_TEXT,
        )
    ]
    assert score_all(cases, recordings)[0].passed is False
    assert score_all(cases, recordings, source="parsed")[0].passed is True


# --- Scoring one case ----------------------------------------------------------


def test_the_right_record_passes():
    score = score_case(
        _case(ExpectedIdentity(status="found", acceptable_dois=[_TPAMI_DOI])),
        [_candidate()],
    )
    assert score.passed is True
    assert score.actual_status == "found"
    assert score.rule == "exact-title"
    assert score.selected_id == _TPAMI_DOI


def test_the_wrong_status_fails_and_names_both(tmp_path):
    score = score_case(_case(ExpectedIdentity(status="not_found")), [_candidate()])
    assert score.passed is False
    assert score.expected_status == "not_found"
    assert score.actual_status == "found"
    assert "expected not_found, got found" in score.detail


def test_selecting_a_forbidden_record_fails_though_the_status_is_right():
    # The point of forbidden_dois. The rule answers found, which is the right
    # status, on a record the annotation says is not the cited work -- here the
    # conference version of a journal article. A status-only check scores this
    # correct and the fixture stops measuring anything.
    cvpr = _candidate(doi="10.1109/CVPR.2012.6248012", record_id="cvpr-2012", venue=_CVPR)
    case = _case(
        ExpectedIdentity(status="found", forbidden_dois=["10.1109/CVPR.2012.6248012"])
    )
    score = score_case(case, [cvpr])
    assert score.actual_status == "found"
    assert score.passed is False
    assert "forbidden" in score.detail


def test_a_forbidden_doi_prefix_fails_a_selection():
    # The measured spoof registers its records under the 10.65215 prefix, so the
    # fixture forbids the prefix rather than enumerating the records. The record
    # here carries a venue, which the real one does not, so that the selection
    # happens and the prefix check is the thing under test.
    spoof = _candidate(
        doi="10.65215/xyz",
        record_id="W7123456789",
        title="Attention is all you need",
        year=2017,
        venue=_NEURIPS,
    )
    case = _case(
        ExpectedIdentity(status="found", forbidden_doi_prefixes=["10.65215"]),
        query=_query(title="Attention is all you need", year=2017, venue=_NEURIPS),
    )
    score = score_case(case, [spoof])
    assert score.actual_status == "found"
    assert score.passed is False
    assert score.selected_id == "10.65215/xyz"


def test_a_found_record_that_is_not_acceptable_fails():
    other = _candidate(doi="10.1109/TPAMI.2015.9999999", record_id="other", year=2015)
    case = _case(
        ExpectedIdentity(status="found", acceptable_dois=[_TPAMI_DOI]),
        query=_query(year=None),
    )
    score = score_case(case, [other])
    assert score.actual_status == "found"
    assert score.passed is False
    assert "not an acceptable answer" in score.detail


def test_an_acceptable_doi_matches_through_its_url_form():
    # Provider records carry DOIs as URLs and the fixture carries them bare;
    # comparing the raw strings would fail every case for a formatting reason.
    case = _case(
        ExpectedIdentity(status="found", acceptable_dois=["https://doi.org/10.1109/TPAMI.2014.2361319"])
    )
    assert score_case(case, [_candidate()]).passed is True


def test_a_record_with_no_doi_is_named_by_its_record_id():
    preprint = _candidate(doi="", record_id="W2963472678")
    case = _case(ExpectedIdentity(status="found", acceptable_dois=["W2963472678"]))
    score = score_case(case, [preprint])
    assert score.passed is True
    assert score.selected_id == "W2963472678"


def test_a_case_with_no_acceptable_dois_still_passes_on_its_status():
    # "Not yet annotated" is not "no right answer"; the case is scored, and the
    # report says out loud how many cases this covers.
    score = score_case(_case(ExpectedIdentity(status="found")), [_candidate()])
    assert score.passed is True
    assert score.selected_id == _TPAMI_DOI


def test_an_ambiguous_answer_that_was_expected_passes():
    # Two distinct works with the same title -- a different first author keeps
    # them from being folded into one -- and no venue on the reference to
    # separate them with, so abstaining is the right answer.
    twin = _candidate(
        doi="10.1109/CVPR.2012.6248012",
        record_id="cvpr",
        authors=["Someone Else"],
        venue=_CVPR,
    )
    case = _case(ExpectedIdentity(status="ambiguous"), query=_query(venue=""))
    score = score_case(case, [_candidate(), twin])
    assert score.actual_status == "ambiguous"
    assert score.passed is True


def test_a_case_with_no_recording_is_scored_against_nothing():
    # Stated rather than hidden. A missing recording and a provider that
    # returned nothing are indistinguishable here, which is why the harness
    # warns about the first instead of quietly scoring it.
    score = score_all([_case(ExpectedIdentity(status="not_found"))], {})[0]
    assert score.actual_status == "not_found"
    assert score.passed is True


# --- Cases that carry their own candidates -------------------------------------


def _inline_case(candidates, expected, *, case_id="handwritten-1"):
    case = _case(expected, case_id=case_id)
    case.candidates = candidates
    return case


def test_a_case_that_carries_its_own_candidates_wins_over_the_recordings():
    # The whole reason hand-written cases exist: a fabricated record arriving on
    # its own is not something a live query can be asked to reproduce, since live
    # it arrives among four real ones.
    case = _inline_case([_candidate()], ExpectedIdentity(status="found"))
    assert candidates_for(case, {"handwritten-1": []}) == [_candidate()]


def test_a_case_with_an_empty_candidate_set_is_not_read_as_having_none():
    case = _inline_case([], ExpectedIdentity(status="not_found"))
    recordings = {"handwritten-1": [_candidate()]}
    assert candidates_for(case, recordings) == []
    assert score_all([case], recordings)[0].actual_status == "not_found"


def test_a_case_without_its_own_candidates_reads_the_recording():
    case = _case(ExpectedIdentity(status="found"))
    assert candidates_for(case, {"f940bcbf-1": [_candidate()]}) == [_candidate()]


def test_inline_candidates_survive_the_fixture_round_trip(tmp_path):
    payload = {
        **_CASE_PAYLOAD,
        "candidates": [candidate_to_dict(_candidate())],
    }
    case = load_cases(_write(tmp_path, [payload]))[0]
    assert case.candidates == [_candidate()]


def test_a_case_with_no_candidates_key_reads_the_recordings(tmp_path):
    case = load_cases(_write(tmp_path, [_CASE_PAYLOAD]))[0]
    assert case.candidates is None


# --- Summarising ---------------------------------------------------------------


_UNSET = object()


def _annotated(case_id, *, status="found", acceptable=_UNSET, forbidden=None):
    # A sentinel rather than a None default, because "no acceptable DOI given"
    # and "explicitly annotated as having none" are different cases and an
    # `or` default cannot tell them apart.
    if acceptable is _UNSET:
        acceptable = [_TPAMI_DOI] if status == "found" else []
    return _case(
        ExpectedIdentity(
            status=status,
            acceptable_dois=list(acceptable),
            forbidden_dois=forbidden or [],
        ),
        case_id=case_id,
    )


def test_precision_and_recall_count_only_annotated_cases():
    # The unannotated case is answered found and scored a pass, but it is not
    # evidence of precision: nobody has said yet which record would be right.
    cases = [
        _annotated("hit"),
        _annotated("missed"),
        _annotated("unannotated", acceptable=[]),
    ]
    scores = [
        _score("hit", True),
        _score("missed", False, status="not_found"),
        _score("unannotated", True),
    ]
    report = summarize(cases, scores)
    assert report.total == 3
    assert report.passed == 2
    assert report.failed == 1
    assert report.precision == 1.0
    assert report.recall == 0.5
    assert report.unannotated == 1


def test_a_found_answer_where_none_was_expected_costs_precision():
    cases = [_annotated("hit"), _annotated("spurious", status="not_found")]
    report = summarize(cases, [_score("hit", True), _score("spurious", False)])
    assert report.precision == 0.5
    assert report.recall == 1.0


def test_a_missed_reference_costs_recall():
    cases = [_annotated("hit"), _annotated("missed")]
    report = summarize(cases, [_score("hit", True), _score("missed", False, status="not_found")])
    assert report.precision == 1.0
    assert report.recall == 0.5


def test_precision_and_recall_are_absent_when_nothing_was_annotated():
    cases = [_annotated("unannotated", acceptable=[])]
    report = summarize(cases, [_score("unannotated", True)])
    assert report.precision is None
    assert report.recall is None
    assert report.unannotated == 1


def test_an_ambiguous_expectation_stays_out_of_precision_and_recall():
    cases = [_annotated("ambiguous", status="ambiguous", acceptable=[_TPAMI_DOI])]
    report = summarize(cases, [_score("ambiguous", True, status="ambiguous")])
    assert report.passed == 1
    assert report.precision is None
    assert report.recall is None
    assert report.unannotated == 0


def test_the_report_counts_which_rule_decided():
    # This counter is how the question "does this tier ever fire?" gets answered
    # from a report rather than from an opinion. It is what showed the fuzzy tier
    # never decided a case, which is why there is no longer one to count.
    cases = [_annotated("a"), _annotated("b")]
    scores = [
        _score("a", True, rule="exact-title"),
        _score("b", True, rule="exact-title"),
    ]
    assert summarize(cases, scores).rules == {"exact-title": 2}
    assert summarize(cases, [_score("a", True, rule="doi"), *scores[1:]]).rules == {
        "doi": 1,
        "exact-title": 1,
    }
    assert summarize(cases, scores).actual_statuses == {"found": 2}


# --- The threshold sweep -------------------------------------------------------


def test_sweep_values_covers_both_ends_with_no_float_noise():
    values = sweep_values(0.50, 0.95, 0.01)
    assert len(values) == 46
    assert values[0] == 0.5
    assert values[-1] == 0.95
    assert 0.7 in values
    assert sweep_values(0.0, 0.2, 0.05) == [0.0, 0.05, 0.1, 0.15, 0.2]


def test_a_sweep_step_of_zero_is_rejected():
    with pytest.raises(ValueError):
        sweep_values(0.5, 0.9, 0)


# The real reference the year rule exists for: backend/uploads/parsed/f940bcbf #1,
# whose record one provider dates 2015 where the reference says 2014.
_LATE_YEAR = 2015
_OLD_YEAR = 2012


def _year_setup():
    """The reference against the record a provider dates one year late."""
    late = _candidate(doi="10.1/late", record_id="10.1/late", year=_LATE_YEAR)
    case = _case(ExpectedIdentity(status="found", acceptable_dois=["10.1/late"]))
    return case, late


def _superseded_setup():
    """The reference against a record two years out, which is a different work."""
    old = _candidate(doi="10.1/old", record_id="10.1/old", year=_OLD_YEAR)
    case = _case(ExpectedIdentity(status="not_found", forbidden_dois=["10.1/old"]))
    return case, old


def test_sweeping_the_year_tolerance_reports_the_case_it_flips():
    case, late = _year_setup()
    points = sweep_threshold([case], {case.case_id: [late]}, sweep_values(0.0, 3.0, 1.0))
    at = {point.value: point for point in points}

    # The record is the cited work and its title matches exactly, so only the
    # year veto can reject it. Tightening the tolerance to 0 does.
    assert at[0.0].passed == 0
    assert at[1.0].passed == 1
    assert at[1.0].flips == [case.case_id]
    assert at[2.0].passed == 1
    assert at[2.0].flips == []


def test_sweeping_the_year_tolerance_past_its_pin_admits_a_superseded_record():
    case, old = _superseded_setup()
    points = sweep_threshold([case], {case.case_id: [old]}, sweep_values(0.0, 3.0, 1.0))
    at = {point.value: point for point in points}

    # Two years out is rejected at the measured tolerance, and admitted at 2,
    # where the same case fails by selecting a record the annotation forbids.
    assert at[1.0].passed == 1
    assert at[2.0].passed == 0
    assert at[2.0].flips == [case.case_id]


def test_the_sweep_leaves_the_constant_where_it_found_it():
    case, late = _year_setup()
    before = identity.YEAR_TOLERANCE
    sweep_threshold([case], {case.case_id: [late]}, [0, 3])
    assert identity.YEAR_TOLERANCE == before


def test_the_sweep_restores_the_constant_even_when_scoring_raises():
    def _explode(*args, **kwargs):
        raise RuntimeError("scoring failed")

    with patch("engine.metadata_eval.score_all", side_effect=_explode):
        with pytest.raises(RuntimeError):
            sweep_threshold([], {}, [0])
    assert identity.YEAR_TOLERANCE == 1


def test_sweeping_an_unknown_attribute_is_not_silently_ignored():
    with pytest.raises(AttributeError):
        sweep_threshold([], {}, [0], attribute="NOT_A_CONSTANT")


# --- Rendering -----------------------------------------------------------------


def _report(**overrides):
    cases = [_annotated("hit"), _annotated("miss", status="not_found")]
    scores = [
        _score("hit", True),
        _score(
            "miss",
            False,
            rule="title-overlap",
            selected="10.1/wrong",
            detail="expected not_found, got found: 0.71 token overlap",
        ),
    ]
    report = summarize(cases, scores)
    for name, value in overrides.items():
        setattr(report, name, value)
    return report


def test_the_report_states_the_metrics_and_the_failing_case():
    from engine.metadata_eval import render_report

    text = render_report(_report(), title="identity replay", source="fixture")
    assert "identity replay" in text
    assert "cases        : 2  passed 1  failed 1" in text
    assert "precision    : 50.0%" in text
    assert "recall       : 100.0%" in text
    assert "rules        : exact-title=1, title-overlap=1" in text
    assert "miss: expected not_found, got found" in text


def test_the_report_says_out_loud_how_many_cases_were_unannotated():
    from engine.metadata_eval import render_report

    text = render_report(_report(unannotated=3), title="t", source="fixture")
    assert "unannotated  : 3 case(s)" in text
    assert "excluded from precision and recall" in text


def test_the_report_says_when_a_metric_could_not_be_computed():
    from engine.metadata_eval import render_report

    text = render_report(_report(precision=None, recall=None), title="t", source="fixture")
    assert text.count("n/a") == 2


def test_the_sweep_table_has_a_row_per_value_and_names_the_flips():
    from engine.metadata_eval import render_sweep

    case, late = _year_setup()
    points = sweep_threshold([case], {case.case_id: [late]}, sweep_values(0.0, 1.0, 1.0))
    text = render_sweep(points, attribute="YEAR_TOLERANCE")
    assert "sweep of YEAR_TOLERANCE" in text
    lines = text.strip().splitlines()
    assert len(lines) == 2 + 2
    assert lines[-1].strip().endswith(case.case_id)
    assert lines[2].strip().endswith("-")


# --- Recordings ----------------------------------------------------------------


def test_a_candidate_survives_a_round_trip_through_its_recorded_form():
    candidate = _candidate(arxiv_id="1312.5663", url="https://arxiv.org/abs/1312.5663")
    assert candidate_from_dict(candidate_to_dict(candidate)) == candidate


def test_recordings_are_loaded_by_case_id(tmp_path):
    save_recording(tmp_path, "f940bcbf-1", {"candidates": [candidate_to_dict(_candidate())]})
    save_recording(tmp_path, "92574678-58", {"candidates": []})
    recordings = load_recordings(tmp_path)
    assert sorted(recordings) == ["92574678-58", "f940bcbf-1"]
    assert recordings["f940bcbf-1"] == [_candidate()]
    assert recordings["92574678-58"] == []


def test_a_recording_carries_the_query_it_was_made_with(tmp_path):
    save_recording(
        tmp_path,
        "c",
        {"query": {"title": "x"}, "candidates": [candidate_to_dict(_candidate())]},
    )
    assert load_recordings(tmp_path)["c"] == [_candidate()]
