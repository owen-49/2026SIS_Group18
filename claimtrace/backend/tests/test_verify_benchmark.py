"""Tests for verify_benchmark.py — the Verify accuracy/time instrument.

Everything here is worked out by hand from a constructed recording, so a failure
means the arithmetic moved rather than that the endpoint did. The two rules worth
breaking on purpose are covered from both sides: a status that is not COMPARED
never carries a verdict, and a file this script writes never carries a key.

The live half cannot run in CI -- it spends the user's credits and it measures
the runner -- so the offline half carries the checks: the request plan, the
recording's shape, the arithmetic over a recording, and the timing summariser.
"""

import json

import pytest
from backend.scripts.verify_benchmark import (
    COMPARISON_STATUSES,
    Planned,
    _assert_no_secret_keys,
    assert_no_secret,
    assert_unique_claims,
    check,
    entries_by_pair,
    estimate,
    judge_from,
    load_corpus,
    passages_by_paper,
    percentile,
    plan_requests,
    resolve_corpus_key,
    resolve_sources,
    retrieve_from,
    timing_report,
    write_json,
)
from backend.src.models import ComparisonStatus
from engine.passage_eval import (
    AnnotatedPair,
    score_retrieval,
    score_verdicts,
)

# --- Builders -------------------------------------------------------------------


def _pair(claim, *, source_paper="", marker="", pair_id="", label="", passage=""):
    return AnnotatedPair(
        claim=claim,
        source_paper=source_paper,
        citation_marker=marker,
        pair_id=pair_id,
        label=label,
        source_passage=passage,
    )


def _record(paper_id, *, scope=None, filename="paper.pdf", file_type="pdf"):
    return {
        "paper_id": paper_id,
        "scope": scope,
        "file_type": file_type,
        "original_filename": filename,
        "file_path": f"/uploads/{paper_id}.pdf",
    }


def _entry(claim, status, verdict="", *, pair_id="", evidence=(), seconds=1.0, **extra):
    item = {
        "pair_id": pair_id or claim,
        "claim": claim,
        "status": status,
        "verdict": verdict,
        "evidence": [
            {"rank": index, "page": 1, "similarity": 0.5, "passage_text": text}
            for index, text in enumerate(evidence, start=1)
        ],
        "seconds": seconds,
    }
    item.update(extra)
    return item


def _run(entries, *, k=5, components=()):
    return {"k": k, "pairs": list(entries), "components": list(components)}


# --- The status vocabulary ------------------------------------------------------


def test_the_restated_statuses_are_the_models_own():
    """The copy exists so replay needs no FastAPI; this is what keeps it a copy."""
    assert COMPARISON_STATUSES == tuple(status.value for status in ComparisonStatus)


# --- Which source a pair is sent against ----------------------------------------


def test_a_pair_naming_a_verify_source_resolves_to_itself():
    records = [_record("aaaa1111", scope="verify_source")]
    mapping, needs = resolve_sources([_pair("c", source_paper="aaaa1111")], records)
    assert mapping == {"aaaa1111": "aaaa1111"}
    assert needs == {}


def test_a_library_paper_finds_its_verify_twin_by_filename():
    records = [
        _record("lib11111", filename="1907.05242v2.pdf"),
        _record("ver22222", scope="verify_source", filename="1907.05242v2.pdf"),
    ]
    mapping, needs = resolve_sources([_pair("c", source_paper="lib11111")], records)
    assert mapping == {"lib11111": "ver22222"}
    assert needs == {}


def test_a_library_paper_with_no_twin_is_reported_for_upload():
    records = [
        _record("lib11111", filename="lewis.pdf"),
        _record("ver22222", scope="verify_source", filename="other.pdf"),
    ]
    mapping, needs = resolve_sources([_pair("c", source_paper="lib11111")], records)
    assert mapping == {}
    assert set(needs) == {"lib11111"}
    assert needs["lib11111"]["original_filename"] == "lewis.pdf"


def test_two_uploads_of_one_pdf_resolve_to_the_same_copy_every_time():
    """A paper uploaded twice must not pick a different copy per machine."""
    records = [
        _record("zzz99999", scope="verify_source", filename="realm.pdf"),
        _record("aaa11111", scope="verify_source", filename="realm.pdf"),
        _record("lib22222", filename="realm.pdf"),
    ]
    mapping, _ = resolve_sources([_pair("c", source_paper="lib22222")], records)
    assert mapping == {"lib22222": "aaa11111"}


def test_a_source_key_matching_no_record_is_neither_resolved_nor_uploaded():
    records = [_record("aaaa1111", scope="verify_source")]
    mapping, needs = resolve_sources([_pair("c", source_paper="nope")], records)
    assert mapping == {} and needs == {}


# --- The request plan -----------------------------------------------------------


def test_a_resolved_pair_is_sent_by_source_id_with_the_pair_id_echoed():
    planned = plan_requests(
        [_pair("the claim", source_paper="k", marker="[12]", pair_id="rag-x-0")],
        {"k": "ver1"},
        {"ver1": ["a passage"]},
    )[0]
    assert planned.path == "source_paper_id"
    assert planned.body["source_paper_id"] == "ver1"
    assert planned.body["claim_id"] == "rag-x-0"
    assert planned.body["citation_marker"] == "[12]"
    assert planned.body["k"] == 5
    assert planned.calls_the_model


def test_a_pair_with_no_marker_still_sends_a_usable_one():
    """The request model requires a marker; this branch resolves none."""
    planned = plan_requests(
        [_pair("the claim", source_paper="k")], {"k": "ver1"}, {"ver1": ["a passage"]}
    )[0]
    assert planned.body["citation_marker"] == "manual"
    assert "claim_id" not in planned.body


def test_a_source_with_no_parsed_text_is_predicted_to_abstain():
    planned = plan_requests(
        [_pair("the claim", source_paper="k")], {"k": "ver1"}, {"other": ["text"]}
    )[0]
    assert planned.sends
    assert planned.predicted_abstention.startswith("SOURCE_EMPTY")
    assert planned.calls_the_model  # it does reach the model; it just cannot judge


def test_a_pending_upload_is_a_step_rather_than_a_gap():
    record = _record("lib11111")
    planned = plan_requests(
        [_pair("the claim", source_paper="lib11111")],
        {},
        {"lib11111-full": ["text"]},
        pending_uploads={"lib11111": record},
    )[0]
    assert planned.sends
    assert "register" in planned.note
    assert planned.calls_the_model
    assert planned.body == {}  # built after the upload, when the id exists


def test_an_unresolvable_source_is_blocked_and_carries_the_route_to_fix_it():
    planned = plan_requests([_pair("the claim", source_paper="lib11111")], {}, {})[0]
    assert not planned.sends
    assert "POST /api/verify/sources" in planned.blocked
    assert not planned.calls_the_model


def test_a_marker_pair_falls_back_to_the_manuscript_when_one_is_named():
    planned = plan_requests(
        [_pair("the claim", source_paper="lib11111", marker="(Wei, 2022)")],
        {},
        {},
        manuscript_id="ms-1",
    )[0]
    assert planned.path == "citation_marker"
    assert planned.body["manuscript_id"] == "ms-1"
    assert not planned.calls_the_model  # the estimate cannot know it reaches the model
    assert planned.predicted_abstention.startswith("unpredictable")


def test_a_pair_naming_no_source_at_all_is_blocked():
    planned = plan_requests([_pair("the claim")], {}, {})[0]
    assert planned.blocked == "the pair names no source paper"


# --- The estimate ---------------------------------------------------------------


def test_the_estimate_counts_the_calls_and_reports_the_gaps(capsys):
    planned = [
        Planned(pair=_pair("a"), path="source_paper_id"),
        Planned(pair=_pair("b"), path="source_paper_id", predicted_abstention="SOURCE_EMPTY"),
        Planned(pair=_pair("c"), blocked="no source"),
    ]
    status = estimate(
        [_pair("a"), _pair("b"), _pair("c")],
        planned,
        mapping={"k": "v"},
        needs_upload={"lib": _record("lib")},
    )
    printed = capsys.readouterr().out
    assert status == 1  # a blocked pair is a gap, so the exit code says so
    assert "LLM calls    : 2" in printed  # both sent pairs reach the model
    assert "abstentions  : 1" in printed
    assert "blocked      : 1" in printed
    assert "upload lib" in printed


# --- Uniqueness -----------------------------------------------------------------


def test_two_pairs_with_the_same_claim_stop_the_run():
    with pytest.raises(SystemExit, match="same claim text"):
        assert_unique_claims([_pair("same"), _pair("same")])


def test_distinct_claims_pass_the_uniqueness_check():
    assert_unique_claims([_pair("one"), _pair("two")])


# --- Secrets --------------------------------------------------------------------


def test_a_key_nested_in_a_response_fails_the_write():
    message = "auth failed for sk-live-abcdefghijklmnop"
    with pytest.raises(SystemExit, match="contains the API key"):
        assert_no_secret({"message": message}, ["sk-live-abcdefghijklmnop"], "x")


def test_a_clean_payload_passes_the_key_scan():
    assert_no_secret({"message": "ok", "evidence": [{"passage_text": "text"}]}, ["secret"], "x")


def test_an_ai_config_field_is_refused_by_name():
    with pytest.raises(SystemExit, match="api_key"):
        _assert_no_secret_keys({"detail": {"api_key": "anything"}}, "x")


def test_a_key_looking_value_is_refused_even_when_the_key_is_unknown():
    """Replay has no key in hand, so the shapes stand in for the value."""
    with pytest.raises(SystemExit, match="looks like a key"):
        _assert_no_secret_keys({"message": "sk-proj-abcdefghijklmnopqrstuvwx"}, "x")


def test_a_passage_that_merely_mentions_a_prefix_is_not_a_key():
    _assert_no_secret_keys({"passage_text": "the sk- prefix appears in prose"}, "x")


def test_writing_refuses_to_replace_a_recording_without_permission(tmp_path):
    target = tmp_path / "verify_run.json"
    write_json(target, {"pairs": []}, [])
    with pytest.raises(SystemExit, match="already exists"):
        write_json(target, {"pairs": [1]}, [], overwrite=False)


def test_a_written_recording_round_trips(tmp_path):
    target = tmp_path / "verify_run.json"
    write_json(target, {"pairs": [{"claim": "c"}]}, [])
    assert json.loads(target.read_text(encoding="utf-8"))["pairs"] == [{"claim": "c"}]


# --- Scoring a recording by hand ------------------------------------------------


def _three_pair_run():
    entries = [
        _entry(
            "claim a",
            "COMPARED",
            "SUPPORT",
            pair_id="a",
            evidence=["the alpha passage", "a beta passage"],
        ),
        _entry("claim b", "COMPARED", "SUPPORT", pair_id="b", evidence=["a beta passage"]),
        _entry("claim c", "SOURCE_EMPTY", "", pair_id="c"),
    ]
    pairs = [
        _pair("claim a", source_paper="p1", passage="alpha", label="SUPPORT", pair_id="a"),
        _pair("claim b", source_paper="p1", passage="beta", label="CONTRADICT", pair_id="b"),
        _pair("claim c", source_paper="p1", passage="gamma", label="NOT_FOUND", pair_id="c"),
    ]
    corpus = {"p1-full": ["the alpha passage", "a beta passage", "nothing else"]}
    return pairs, entries, corpus


def test_retrieval_and_verdicts_score_by_hand():
    pairs, entries, corpus = _three_pair_run()
    entries = entries_by_pair([_run(entries)])

    retrieval = score_retrieval(pairs, passages_by_paper(pairs, corpus), retrieve_from(entries))
    # a and b both rank 1; c's marked passage was never retrieved
    assert (retrieval.scored, retrieval.recall_at_1, retrieval.recall_at_5) == (3, 0.6667, 0.6667)

    verdicts = score_verdicts(pairs, judge_from(entries))
    assert (verdicts.judged, verdicts.abstained, verdicts.unannotated) == (2, 1, 0)
    assert verdicts.accuracy == 0.5  # one of the two judged pairs is wrong
    assert verdicts.f1_support_vs_rest == 0.6667
    assert verdicts.kappa == 0.0  # observed 0.5 against a chance agreement of 0.5
    assert verdicts.abstention_statuses == {"SOURCE_EMPTY": 1}
    assert verdicts.confusion == {"SUPPORT": {"SUPPORT": 1}, "CONTRADICT": {"SUPPORT": 1}}


def test_an_unrecorded_pair_scores_as_an_abstention_not_an_error():
    pairs, _, corpus = _three_pair_run()
    verdicts = score_verdicts(pairs, judge_from({}))
    assert (verdicts.judged, verdicts.abstained) == (0, 3)
    assert verdicts.accuracy is None
    assert verdicts.abstention_statuses == {"NO_RECORDING": 3}


def test_a_verdict_under_a_non_compared_status_is_not_read():
    """The contract's rule, at the one place that could break it."""
    entries = entries_by_pair([_run([_entry("claim a", "LLM_FAILED", "SUPPORT", pair_id="a")])])
    judgement = judge_from(entries)(_pair("claim a", pair_id="a"))
    assert judgement.predicted == ""
    assert judgement.status == "LLM_FAILED"


def test_the_deepest_recording_of_a_pair_wins():
    shallow = _entry("claim a", "COMPARED", "SUPPORT", pair_id="a", evidence=["one"])
    deep = _entry("claim a", "COMPARED", "PARTIAL", pair_id="a", evidence=["one", "two"])
    entries = entries_by_pair([_run([deep], k=5), _run([shallow], k=1)])
    assert entries["a"]["verdict"] == "PARTIAL"
    assert len(entries["a"]["evidence"]) == 2


def test_a_tie_goes_to_the_earlier_run():
    first = _entry("claim a", "COMPARED", "SUPPORT", pair_id="a")
    second = _entry("claim a", "COMPARED", "CONTRADICT", pair_id="a")
    entries = entries_by_pair([_run([first], k=5), _run([second], k=5)])
    assert entries["a"]["verdict"] == "SUPPORT"


def test_retrieval_truncates_the_recording_at_the_depth_asked_for():
    entries = entries_by_pair(
        [_run([_entry("claim a", "COMPARED", "SUPPORT", pair_id="a", evidence=["x", "y", "z"])])]
    )
    assert retrieve_from(entries)("claim a", [], 2) == ["x", "y"]


# --- Timing ---------------------------------------------------------------------


def test_the_nearest_rank_percentile_is_the_one_defined():
    values = [1.0, 2.0, 3.0, 4.0]
    assert percentile(values, 0.5) == 2.0  # ceil(0.5 x 4) = rank 2
    assert percentile(values, 0.95) == 4.0  # ceil(0.95 x 4) = rank 4
    assert percentile(values, 1.0) == 4.0
    assert percentile([], 0.5) is None


def test_the_first_call_is_held_out_of_the_summary():
    run = _run(
        [
            _entry("a", "COMPARED", "SUPPORT", pair_id="a", seconds=9.0),
            _entry("b", "COMPARED", "SUPPORT", pair_id="b", seconds=2.0),
            _entry("c", "COMPARED", "SUPPORT", pair_id="c", seconds=4.0),
        ]
    )
    timing = timing_report([run])
    assert timing["first_call"] == 9.0
    assert timing["http"]["n"] == 3 and timing["http"]["max"] == 9.0
    assert timing["steady"] == {
        "n": 2,
        "min": 2.0,
        "median": 2.0,
        "p95": 4.0,
        "max": 4.0,
    }


def test_the_residual_is_the_steady_median_minus_the_component_median():
    run = _run(
        [
            _entry("a", "COMPARED", "SUPPORT", pair_id="a", seconds=8.0),
            _entry("b", "COMPARED", "SUPPORT", pair_id="b", seconds=3.0),
            _entry("c", "COMPARED", "SUPPORT", pair_id="c", seconds=5.0),
        ],
        components=[
            {"pair_id": "b", "source_passages": 10, "seconds": 1.0},
            {"pair_id": "c", "source_passages": 277, "seconds": 2.0},
        ],
    )
    timing = timing_report([run])
    # nearest rank: two component calls, so the median is the lower one, 1.0
    assert timing["component"]["median"] == 1.0
    assert timing["llm_residual_median"] == 2.0  # steady median 3.0 - 1.0
    assert set(timing["component"]["by_source_passages"]) == {"10", "277"}


def test_the_timing_groups_by_status_and_by_source():
    run = _run(
        [
            _entry("a", "COMPARED", "SUPPORT", pair_id="a", seconds=1.0, source_paper="rag"),
            _entry("b", "SOURCE_EMPTY", "", pair_id="b", seconds=5.0, source_paper="rag"),
            _entry("c", "COMPARED", "PARTIAL", pair_id="c", seconds=3.0, source_paper="realm"),
        ]
    )
    timing = timing_report([run])
    assert timing["by_status"]["COMPARED"]["n"] == 2
    assert timing["by_status"]["SOURCE_EMPTY"]["n"] == 1
    assert timing["by_source"]["rag"]["max"] == 5.0
    assert timing["by_k"] == {"5": timing["http"]}


# --- The recording checks -------------------------------------------------------


def test_a_clean_recording_passes_every_check():
    run = _run(
        [
            _entry("a", "COMPARED", "SUPPORT", pair_id="a", evidence=["one"]),
            _entry("b", "MANUAL_SOURCE_NOT_FOUND", "", pair_id="b"),
        ]
    )
    assert check([run]) == []


def test_an_invented_verdict_fails_the_check():
    run = _run([_entry("a", "LLM_FAILED", "SUPPORT", pair_id="a")])
    problems = check([run])
    assert any("only COMPARED produces a judgement" in problem for problem in problems)


def test_an_unknown_status_fails_the_check():
    run = _run([_entry("a", "MADE_UP", "", pair_id="a")])
    assert any("unknown status" in problem for problem in check([run]))


def test_a_compared_entry_with_no_verdict_fails_the_check():
    run = _run([_entry("a", "COMPARED", "", pair_id="a", evidence=["one"])])
    problems = check([run])
    assert any("COMPARED with no verdict" in problem for problem in problems)


def test_evidence_ranks_must_run_from_one():
    entry = _entry("a", "COMPARED", "SUPPORT", pair_id="a", evidence=["one", "two"])
    entry["evidence"][1]["rank"] = 7
    problems = check([_run([entry])])
    assert any("not 1..n" in problem for problem in problems)


def test_a_missing_pair_id_fails_the_check():
    entry = _entry("a", "COMPARED", "SUPPORT", pair_id="a", evidence=["one"])
    entry["pair_id"] = ""
    problems = check([_run([entry])])
    assert any("no pair_id" in problem for problem in problems)


def test_a_missing_duration_fails_the_check():
    entry = _entry("a", "COMPARED", "SUPPORT", pair_id="a", evidence=["one"], seconds=None)
    problems = check([_run([entry])])
    assert any("no recorded duration" in problem for problem in problems)


def test_a_recording_without_a_depth_fails_the_check():
    run = _run([_entry("a", "COMPARED", "SUPPORT", pair_id="a", evidence=["one"])])
    del run["k"]
    assert any("retrieval depth k" in problem for problem in check([run]))


# --- The corpus view ------------------------------------------------------------


def test_the_corpus_loader_reads_paragraphs_and_skips_the_rest(tmp_path):
    (tmp_path / "paper.json").write_text(
        json.dumps({"paragraphs": [{"text": "one"}, {"text": " "}, {"text": "two"}]}),
        encoding="utf-8",
    )
    (tmp_path / "x.references.json").write_text("{not json", encoding="utf-8")
    (tmp_path / "empty.json").write_text(json.dumps({"paragraphs": []}), encoding="utf-8")
    corpus = load_corpus(tmp_path)
    assert corpus == {"paper": ["one", "two"]}
    assert resolve_corpus_key("pap", corpus) == "paper"
    assert resolve_corpus_key("nope", corpus) == ""
