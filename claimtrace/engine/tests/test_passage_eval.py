"""Tests for passage_eval.py — the claim-passage benchmark instrument.

Every number here is worked out by hand from a constructed pair set, so a
failure means the arithmetic moved rather than that a model did.
"""

import json

import pytest

from engine.passage_eval import (
    ACCURACY_GO,
    DEFAULT_K,
    F1_GO,
    KAPPA_GO,
    LABELS,
    RECALL_AT_1_GO,
    RECALL_AT_1_NO_GO,
    RECALL_AT_5_GO,
    RECALL_AT_5_NO_GO,
    AnnotatedPair,
    Judgement,
    bar_status,
    cohen_kappa,
    find_rank,
    load_pairs,
    normalize_text,
    render_retrieval_report,
    render_verdict_report,
    score_retrieval,
    score_verdicts,
)

_SOURCE = "wei2022emergent"
_GROUND_TRUTH = "the model improves with scale"


# --- Normalisation and ranking --------------------------------------------------


def test_normalisation_folds_case_and_whitespace_runs():
    assert normalize_text("The  Model\n improves") == "the model improves"


def test_normalisation_folds_the_ligature_a_pdf_actually_contains():
    # The manuscript set carries "ﬁxed-length" as one glyph, and an annotator
    # copying from a viewer will produce two characters.
    assert normalize_text("ﬁxed-length") == normalize_text("fixed-length")


def test_the_ground_truth_is_found_inside_a_longer_passage():
    passages = ["unrelated text", "Prefix. The model improves with scale. Suffix."]
    assert find_rank(_GROUND_TRUTH, passages) == 2


def test_a_passage_matching_only_on_case_and_spacing_still_ranks():
    passages = ["THE   MODEL improves with scale"]
    assert find_rank(_GROUND_TRUTH, passages) == 1


def test_a_ground_truth_nothing_contains_has_no_rank():
    assert find_rank(_GROUND_TRUTH, ["a", "b"]) is None


def test_an_empty_ground_truth_matches_nothing_rather_than_everything():
    assert find_rank("   ", ["anything at all"]) is None


# --- Retrieval scoring ----------------------------------------------------------


def _pair(claim, *, passage=_GROUND_TRUTH, paper=_SOURCE, label="SUPPORT"):
    return AnnotatedPair(claim=claim, source_passage=passage, label=label, source_paper=paper)


def _stub_ranking(rankings):
    """A retrieve() that returns a fixed ranking per claim, truncated to k."""

    def retrieve(claim, passages, k):
        return rankings.get(claim, [])[:k]

    return retrieve


def _retrieval_setup():
    # Ranks 1, 3, 5 and a miss: recall@1 is 1/4 and recall@5 is 3/4 by hand.
    rankings = {
        "c1": [_GROUND_TRUTH, "b", "c"],
        "c2": ["a", "b", _GROUND_TRUTH],
        "c3": ["a", "b", "c", "d", f"  {_GROUND_TRUTH.upper()}  "],
        "c4": ["a", "b", "c", "d", "e"],
    }
    passages = {_SOURCE: ["p0", "p1", "p2", "p3", "p4"]}
    return rankings, passages


def test_recall_counts_the_ground_truth_rank_within_the_retrieved_passages():
    rankings, passages = _retrieval_setup()
    pairs = [_pair(claim) for claim in ("c1", "c2", "c3", "c4")]
    report = score_retrieval(pairs, passages, _stub_ranking(rankings))
    assert report.scored == 4
    assert [item.rank for item in report.outcomes] == [1, 3, DEFAULT_K, None]
    assert report.recall_at_1 == 0.25
    assert report.recall_at_5 == 0.75


def test_a_pair_the_corpus_cannot_score_is_held_out_rather_than_counted_a_miss():
    rankings, passages = _retrieval_setup()
    pairs = [
        _pair("c1"),
        _pair("no passage marked", passage=""),
        _pair("paper not loaded", paper="a-paper-with-no-text"),
    ]
    report = score_retrieval(pairs, passages, _stub_ranking(rankings))
    assert report.total == 3
    assert report.scored == 1
    assert report.unscorable == ["no passage marked", "paper not loaded"]
    # Held out of the denominator: 1 of 1, not 1 of 3.
    assert report.recall_at_5 == 1.0


def test_an_empty_pair_set_reports_no_metric_rather_than_zero():
    report = score_retrieval([], {}, _stub_ranking({}))
    assert report.scored == 0
    assert report.recall_at_1 is None
    assert report.recall_at_5 is None


# --- Verdict scoring ------------------------------------------------------------


def _verdict_setup():
    """Six pairs: two right, two wrong, one abstention, one unannotated.

    By hand over the four judged pairs: accuracy 2/4; SUPPORT has one true
    positive, one false positive and one false negative, so F1 is 0.5; kappa is
    (0.5 - 0.375) / (1 - 0.375) = 0.2.
    """
    pairs = [
        _pair("p1", label="SUPPORT"),
        _pair("p2", label="SUPPORT"),
        _pair("p3", label="PARTIAL"),
        _pair("p4", label="NOT_FOUND"),
        _pair("p5", label="CONTRADICT"),
        _pair("p6", label=""),
    ]
    judgements = {
        "p1": Judgement(predicted="SUPPORT", status="JUDGED"),
        "p2": Judgement(predicted="PARTIAL", status="JUDGED"),
        "p3": Judgement(predicted="SUPPORT", status="JUDGED"),
        "p4": Judgement(predicted="NOT_FOUND", status="JUDGED"),
        "p5": Judgement(predicted="", status="NO_CLIENT"),
    }
    return pairs, judgements


def _stub_judge(judgements):
    def judge(pair):
        return judgements.get(pair.claim, Judgement(predicted="", status="MODEL_ERROR"))

    return judge


def test_accuracy_f1_and_kappa_over_the_judged_pairs():
    pairs, judgements = _verdict_setup()
    report = score_verdicts(pairs, _stub_judge(judgements))
    assert report.total == 6
    assert report.judged == 4
    assert report.abstained == 1
    assert report.unannotated == 1
    assert report.accuracy == 0.5
    assert report.f1_support_vs_rest == 0.5
    assert report.kappa == 0.2


def test_an_abstention_is_counted_and_named_rather_than_scored_wrong():
    pairs, judgements = _verdict_setup()
    report = score_verdicts(pairs, _stub_judge(judgements))
    assert report.abstention_statuses == {"NO_CLIENT": 1}
    abstained = [item for item in report.outcomes if item.correct is None]
    assert [item.claim for item in abstained] == ["p5"]


def test_an_unannotated_pair_is_never_put_to_the_judge():
    pairs, judgements = _verdict_setup()
    asked = []

    def judge(pair):
        asked.append(pair.claim)
        return judgements.get(pair.claim, Judgement(predicted="", status="MODEL_ERROR"))

    score_verdicts(pairs, judge)
    assert "p6" not in asked


def test_a_prediction_outside_the_verdict_vocabulary_is_not_scored_either_way():
    # A harness bug rather than a model outcome, so it must not be counted as a
    # correct answer; it lowers coverage, which the report prints.
    pairs = [_pair("p1", label="SUPPORT")]
    report = score_verdicts(
        pairs, _stub_judge({"p1": Judgement(predicted="MAYBE", status="JUDGED")})
    )
    assert report.judged == 0
    assert report.accuracy is None


def test_the_confusion_matrix_places_each_judged_pair_once():
    pairs, judgements = _verdict_setup()
    report = score_verdicts(pairs, _stub_judge(judgements))
    assert report.confusion["SUPPORT"] == {"SUPPORT": 1, "PARTIAL": 1}
    assert report.confusion["PARTIAL"] == {"SUPPORT": 1}
    assert report.confusion["NOT_FOUND"] == {"NOT_FOUND": 1}


def test_no_judged_pair_reports_no_classification_metric():
    report = score_verdicts([], _stub_judge({}))
    assert report.accuracy is None
    assert report.f1_support_vs_rest is None
    assert report.kappa is None
    assert report.confusion == {}


# --- The statistics themselves --------------------------------------------------


def test_kappa_is_zero_when_agreement_matches_chance():
    # Both raters split 5/5 the same way and agree on exactly half the pairs.
    pairs = [("SUPPORT", "SUPPORT")] * 5 + [("SUPPORT", "NOT_FOUND")] * 5
    assert cohen_kappa(pairs) == 0.0


def test_kappa_is_one_when_the_raters_never_disagree():
    pairs = [("SUPPORT", "SUPPORT"), ("PARTIAL", "PARTIAL"), ("NOT_FOUND", "NOT_FOUND")]
    assert cohen_kappa(pairs) == 1.0


def test_kappa_goes_negative_when_agreement_is_worse_than_chance():
    pairs = [("SUPPORT", "NOT_FOUND"), ("NOT_FOUND", "SUPPORT")]
    assert cohen_kappa(pairs) == -1.0


def test_kappa_on_a_single_shared_label_is_undefined_not_zero():
    assert cohen_kappa([("SUPPORT", "SUPPORT"), ("SUPPORT", "SUPPORT")]) is None


# --- Bars -----------------------------------------------------------------------


def test_a_metric_between_the_two_bars_is_called_neither_pass_nor_fail():
    assert bar_status(0.60, RECALL_AT_5_GO, RECALL_AT_5_NO_GO) == "below"
    assert bar_status(RECALL_AT_5_GO, RECALL_AT_5_GO, RECALL_AT_5_NO_GO) == "met"
    assert bar_status(0.49, RECALL_AT_5_GO, RECALL_AT_5_NO_GO) == "no-go"


def test_the_no_go_line_belongs_to_the_band_above_it():
    assert bar_status(RECALL_AT_1_NO_GO, RECALL_AT_1_GO, RECALL_AT_1_NO_GO) == "below"


def test_an_absent_metric_has_no_standing():
    assert bar_status(None, ACCURACY_GO) == "n/a"


def test_the_bars_are_the_ones_the_plan_commits_to():
    assert (RECALL_AT_5_GO, RECALL_AT_5_NO_GO) == (0.80, 0.50)
    assert (RECALL_AT_1_GO, RECALL_AT_1_NO_GO) == (0.50, 0.25)
    assert (ACCURACY_GO, F1_GO, KAPPA_GO) == (0.80, 0.85, 0.70)


def test_the_label_vocabulary_is_the_engines_own_verdict_set():
    assert LABELS == ("SUPPORT", "PARTIAL", "CONTRADICT", "NOT_FOUND")


# --- Loading --------------------------------------------------------------------


def _write(tmp_path, payload):
    path = tmp_path / "pairs.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_a_pair_file_round_trips(tmp_path):
    path = _write(
        tmp_path,
        [
            {
                "claim": "Emergent abilities appear with scale.",
                "source_passage": "Performance improves discontinuously.",
                "label": "SUPPORT",
                "source_paper": "wei2022emergent",
                "annotator": "SL",
            }
        ],
    )
    pair = load_pairs(path)[0]
    assert pair.label == "SUPPORT"
    assert pair.source_paper == "wei2022emergent"
    assert pair.annotator == "SL"


def test_a_lowercase_label_is_accepted_and_normalised(tmp_path):
    assert load_pairs(_write(tmp_path, [{"claim": "c", "label": "partial"}]))[0].label == "PARTIAL"


def test_a_pair_with_no_label_loads_as_unannotated(tmp_path):
    assert load_pairs(_write(tmp_path, [{"claim": "c"}]))[0].label == ""


def test_a_label_the_engine_cannot_emit_is_rejected_rather_than_scored(tmp_path):
    path = _write(tmp_path, [{"claim": "c", "label": "MAYBE"}])
    with pytest.raises(ValueError, match="MAYBE"):
        load_pairs(path)


def test_a_pair_with_no_claim_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="claim"):
        load_pairs(_write(tmp_path, [{"source_passage": "s", "label": "SUPPORT"}]))


def test_an_empty_pair_file_is_a_valid_annotation_target(tmp_path):
    assert load_pairs(_write(tmp_path, [])) == []


def test_a_wrapped_pair_list_is_accepted(tmp_path):
    assert len(load_pairs(_write(tmp_path, {"pairs": [{"claim": "c"}]}))) == 1


def test_a_file_that_is_not_a_pair_list_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="list of pairs"):
        load_pairs(_write(tmp_path, {"pairs": "everything"}))


# --- Rendering ------------------------------------------------------------------


def test_the_retrieval_report_names_each_metric_against_its_bar():
    rankings, passages = _retrieval_setup()
    pairs = [_pair(claim) for claim in ("c1", "c2", "c3", "c4")]
    rendered = render_retrieval_report(score_retrieval(pairs, passages, _stub_ranking(rankings)))
    assert "recall@1     : 25.0%   bar >= 50.0%  [below]" in rendered
    assert "recall@5     : 75.0%   bar >= 80.0%  [below]" in rendered
    assert "unscorable 0" in rendered
    assert "c4" in rendered  # the miss is named


def test_the_retrieval_report_says_so_when_nothing_could_be_scored():
    rendered = render_retrieval_report(score_retrieval([], {}, _stub_ranking({})))
    assert "recall@1     : n/a" in rendered
    assert "nothing was scored" in rendered


def test_the_verdict_report_prints_coverage_beside_the_metrics():
    pairs, judgements = _verdict_setup()
    rendered = render_verdict_report(score_verdicts(pairs, _stub_judge(judgements)))
    assert "coverage     : 80.0%" in rendered
    assert "accuracy     : 50.0%   bar >= 80.0%  [below]" in rendered
    assert "f1 (SUPPORT) : 50.0%   bar >= 85.0%  [below]" in rendered
    assert "kappa        : 20.0%   bar >= 70.0%  [below]" in rendered
    assert "abstentions  : NO_CLIENT=1" in rendered


def test_the_verdict_report_shows_what_was_confused_with_what():
    pairs, judgements = _verdict_setup()
    rendered = render_verdict_report(score_verdicts(pairs, _stub_judge(judgements)))
    assert "expected rows, predicted columns" in rendered
    assert "expected SUPPORT    got PARTIAL" in rendered


def test_the_verdict_report_does_not_report_an_accuracy_over_nothing():
    rendered = render_verdict_report(score_verdicts([], _stub_judge({})))
    assert "accuracy     : n/a" in rendered
    assert "nothing was judged" in rendered
