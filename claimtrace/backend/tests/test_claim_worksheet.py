"""Tests for claim_worksheet.py's merge half -- the last mile of the annotation.

The worksheet itself is a page a person fills in, and its harvest needs network;
neither belongs here. What does belong here is what happens to two filled-in
sheets: which pairs are written, which are held back, and what a re-run does to a
file that already holds pairs. Those are the steps that can silently lose a
person's annotation work.

The module is imported and its ``main`` called directly rather than run as a
subprocess: spawning one costs an interpreter and an engine import per test,
which was twenty-five seconds of this suite, for a ``__main__`` line that is the
same in all four scripts here.

Nothing here touches the committed ``claim_passages.json``: every run names its
own target under ``tmp_path``.
"""

import json

from backend.scripts.claim_worksheet import main


def _pair(pair_id, label="", passage="", *, annotator="", claim="", notes=""):
    return {
        "claim": claim or f"claim {pair_id}",
        "source_passage": passage,
        "label": label,
        "source_paper": "srcdoc1",
        "citing_paper": "cite1",
        "annotator": annotator,
        "notes": notes,
        "pair_id": pair_id,
        "citation_marker": "[1]",
    }


def _sheets(tmp_path, alice, bob):
    first, second = tmp_path / "alice.json", tmp_path / "bob.json"
    first.write_text(json.dumps(alice), encoding="utf-8")
    second.write_text(json.dumps(bob), encoding="utf-8")
    return first, second


def _merge(first, second, *extra):
    return main(["--merge", str(first), str(second), *extra])


def _written(target):
    return json.loads(target.read_text(encoding="utf-8"))


def test_one_merge_reports_every_outcome_and_writes_only_the_agreed(tmp_path, capsys):
    """The four cases in one pair set: agreed, disagreed, contested, unlabelled."""
    first, second = _sheets(
        tmp_path,
        [
            _pair("agreed", "SUPPORT", "the alpha sentence", annotator="alice", notes="it says so"),
            _pair("disagreed", "CONTRADICT", "the beta sentence", annotator="alice"),
            _pair("contested", "PARTIAL", "the gamma sentence", annotator="alice"),
            _pair("unlabelled", "", "", annotator="alice"),
        ],
        [
            _pair("agreed", "SUPPORT", "The  alpha sentence", annotator="bob"),
            _pair("disagreed", "SUPPORT", "the beta sentence", annotator="bob"),
            _pair("contested", "PARTIAL", "another sentence entirely", annotator="bob"),
            _pair("unlabelled", "", "", annotator="bob"),
        ],
    )
    target = tmp_path / "claim_passages.json"
    assert _merge(first, second, "--write", str(target)) == 0
    printed = capsys.readouterr().out

    assert "label agreement: 2/3 = 66.7%" in printed  # only the pairs both labelled
    assert "conflicts      : CONTRADICT vs SUPPORT=1" in printed
    assert "to write     : 2 pair(s) both annotators labelled the same" in printed
    assert "1 disagreeing; adjudicate, then merge again" in printed
    assert "1 not labelled by both yet" in printed
    assert "1 marked two different passages; the first sheet's is kept" in printed

    rows = {row["pair_id"]: row for row in _written(target)}
    assert sorted(rows) == ["agreed", "contested"]
    # A disagreement is absent from the file, not settled by a vote.
    assert "disagreed" not in rows
    assert rows["agreed"]["annotator"] == "alice & bob"
    assert rows["agreed"]["notes"] == "it says so"  # one explanation of one agreed label
    # The sheets wrote the same sentence with different spacing; the first sheet's
    # text is kept rather than a rewritten third version.
    assert rows["agreed"]["source_passage"] == "the alpha sentence"
    assert rows["contested"]["source_passage"] == "the gamma sentence"


def test_a_pair_neither_sheet_reached_stays_out_of_the_file(tmp_path, capsys):
    first, second = _sheets(tmp_path, [_pair("p1", "", "")], [_pair("p1", "", "")])
    target = tmp_path / "claim_passages.json"
    assert _merge(first, second, "--write", str(target)) == 0
    assert "to write     : 0 pair(s) both annotators labelled the same" in capsys.readouterr().out
    assert _written(target) == []


def test_a_passage_one_sheet_left_blank_is_taken_from_the_other(tmp_path):
    first, second = _sheets(
        tmp_path,
        [_pair("p1", "SUPPORT", "", annotator="alice")],
        [_pair("p1", "SUPPORT", "the beta sentence", annotator="bob")],
    )
    target = tmp_path / "claim_passages.json"
    _merge(first, second, "--write", str(target))
    assert _written(target)[0]["source_passage"] == "the beta sentence"


def test_pairs_already_in_the_file_survive_a_merge(tmp_path, capsys):
    """The manual route writes pairs straight into this file; a merge must not eat them."""
    target = tmp_path / "claim_passages.json"
    target.write_text(
        json.dumps([_pair("manual-1", "NOT_FOUND", "hand written", annotator="someone")]),
        encoding="utf-8",
    )
    first, second = _sheets(
        tmp_path,
        [_pair("p1", "SUPPORT", "one", annotator="alice")],
        [_pair("p1", "SUPPORT", "one", annotator="bob")],
    )
    _merge(first, second, "--write", str(target))
    assert "kept         : 1 pair(s)" in capsys.readouterr().out

    rows = {row["pair_id"]: row for row in _written(target)}
    assert sorted(rows) == ["manual-1", "p1"]


def test_merging_again_replaces_the_row_rather_than_appending_it(tmp_path):
    target = tmp_path / "claim_passages.json"
    first, second = _sheets(
        tmp_path,
        [_pair("p1", "SUPPORT", "one", annotator="alice")],
        [_pair("p1", "SUPPORT", "one", annotator="bob")],
    )
    _merge(first, second, "--write", str(target))
    # The pair was adjudicated to a different label; the sheets are re-merged.
    first, second = _sheets(
        tmp_path,
        [_pair("p1", "PARTIAL", "one", annotator="alice")],
        [_pair("p1", "PARTIAL", "one", annotator="bob")],
    )
    _merge(first, second, "--write", str(target))

    rows = _written(target)
    assert len(rows) == 1
    assert rows[0]["label"] == "PARTIAL"


def test_the_written_file_reads_back_as_pairs(tmp_path):
    """The file the merge writes is the file the harness loads."""
    from engine.passage_eval import load_pairs

    target = tmp_path / "claim_passages.json"
    first, second = _sheets(
        tmp_path,
        [_pair("p1", "SUPPORT", "the alpha sentence", annotator="alice")],
        [_pair("p1", "SUPPORT", "the alpha sentence", annotator="bob")],
    )
    _merge(first, second, "--write", str(target))

    pairs = load_pairs(target)
    assert [pair.pair_id for pair in pairs] == ["p1"]
    assert pairs[0].label == "SUPPORT"
    assert pairs[0].source_passage == "the alpha sentence"
    assert pairs[0].annotator == "alice & bob"


def test_without_write_nothing_is_written(tmp_path, capsys):
    """The merge prints by default; a first read of two sheets costs nothing."""
    first, second = _sheets(
        tmp_path,
        [_pair("p1", "SUPPORT", "one", annotator="alice")],
        [_pair("p1", "SUPPORT", "one", annotator="bob")],
    )
    target = tmp_path / "claim_passages.json"
    assert _merge(first, second) == 0
    assert "to write" not in capsys.readouterr().out
    assert not target.exists()


def test_write_without_merge_is_refused(tmp_path, capsys):
    assert main(["--write", str(tmp_path / "x.json")]) == 1
    assert "--write needs --merge" in capsys.readouterr().out
    assert not (tmp_path / "x.json").exists()


def test_a_sheet_without_pair_ids_stops_the_merge(tmp_path, capsys):
    first, second = _sheets(tmp_path, [_pair("", "SUPPORT", "one")], [_pair("", "SUPPORT", "one")])
    target = tmp_path / "claim_passages.json"
    assert _merge(first, second, "--write", str(target)) == 1
    assert "no pair_id" in capsys.readouterr().out
    assert not target.exists()
