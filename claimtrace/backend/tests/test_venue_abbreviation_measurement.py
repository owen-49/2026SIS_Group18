"""Regression tests for the venue-abbreviation measurement proposal."""

from backend.scripts.venue_abbreviation_measurement import abbreviation_venues_agree


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
