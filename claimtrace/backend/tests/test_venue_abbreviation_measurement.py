"""Regression tests for the venue-abbreviation measurement proposal."""

import json

from backend.scripts.venue_abbreviation_measurement import (
    _audit_rows,
    abbreviation_venues_agree,
    current_venues_agree,
)


def test_common_venue_abbreviations_match_full_names():
    pairs = [
        (
            "ACL",
            "Proceedings of the 57th Annual Meeting of the Association for "
            "Computational Linguistics (Volume 1: Long Papers)",
        ),
        (
            "EMNLP",
            "Proceedings of the 2018 Conference on Empirical Methods in Natural "
            "Language Processing",
        ),
        ("ICLR", "International Conference on Learning Representations"),
        ("CVPR", "2012 IEEE Conference on Computer Vision and Pattern Recognition"),
        ("TPAMI", "IEEE Transactions on Pattern Analysis and Machine Intelligence"),
        ("NeurIPS", "Advances in Neural Information Processing Systems"),
    ]
    for abbreviation, full_name in pairs:
        assert abbreviation_venues_agree(abbreviation, full_name)


def test_embedded_organisation_acronym_does_not_hide_wrong_conference():
    naacl = (
        "Proceedings of the 2019 Conference of the North American Chapter of the "
        "Association for Computational Linguistics"
    )
    assert not abbreviation_venues_agree("ACL", naacl)


def test_unrelated_and_repository_venues_remain_different():
    assert not abbreviation_venues_agree("ACL", "RAND Corporation eBooks")
    assert not abbreviation_venues_agree("ICLR", "arXiv (Cornell University)")


def test_current_comparator_does_not_gain_unicode_normalisation():
    left = "AAAI Conference on Artiﬁcial Intelligence"
    right = "Proceedings of the AAAI Conference on Artificial Intelligence"
    assert not current_venues_agree(left, right)
    assert not abbreviation_venues_agree(left, right)


def test_audit_rows_deduplicate_repeated_external_records(tmp_path):
    def result(entry_id):
        return {
            "entry": {"entry_id": entry_id},
            "matched_record": {"record_id": "crossref:10.1/example"},
        }

    (tmp_path / "one.json").write_text(
        json.dumps({"input_paper_id": "paper-a", "results": [result("entry-a")]}),
        encoding="utf-8",
    )
    (tmp_path / "two.json").write_text(
        json.dumps({"input_paper_id": "paper-b", "results": [result("entry-b")]}),
        encoding="utf-8",
    )

    files, raw_rows, rows = _audit_rows(tmp_path)

    assert len(files) == 2
    assert raw_rows == 2
    assert len(rows) == 1
