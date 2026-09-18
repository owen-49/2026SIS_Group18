"""Tests for title_matching.py."""

from engine.title_matching import (
    extract_arxiv_id,
    extract_doi,
    first_author_surname,
    normalize_doi,
    normalize_title,
    normalize_venue,
    title_similarity,
    title_tokens,
    venue_match_share,
)


def test_normalize_title_casefolds_and_collapses_whitespace():
    assert normalize_title("  Attention   Is All You Need  ") == "attention is all you need"


def test_normalize_title_repairs_line_wrap_hyphenation():
    # A PDF or container-title line break splits one word across two lines;
    # the hyphen and the break are both removed so the halves rejoin.
    assert normalize_title("Auto- encoders") == "autoencoders"
    # An ordinary hyphen has no following whitespace and is left to the dash pass.
    assert normalize_title("auto-encoders") == "auto encoders"


def test_normalize_title_maps_dash_variants_to_spaces():
    assert normalize_title("K-sparse") == normalize_title("K sparse")
    assert normalize_title("Attention–Based") == normalize_title("Attention Based")


def test_normalize_title_expands_fi_ligature():
    # The fi ligature survives PDF text extraction; NFKC folds it to "fi".
    assert normalize_title("ﬁxed-length") == "fixed length"


def test_normalize_title_strips_punctuation():
    punctuated = normalize_title("Attention Is All You Need!")
    assert punctuated == normalize_title("Attention Is All You Need")


def test_normalize_title_is_empty_for_blank_input():
    assert normalize_title("") == ""
    assert normalize_title("   ") == ""
    assert normalize_title("...") == ""


def test_title_tokens_drops_stop_words():
    assert title_tokens("The inverted multi-index") == {"inverted", "multi", "index"}


def test_title_tokens_keeps_short_acronyms():
    # Mirroring the backend's len(token) > 2 filter would make these equal.
    assert title_tokens("AI for Search") == {"ai", "search"}
    assert title_tokens("ML for Search") == {"ml", "search"}
    assert title_tokens("AI for Search") != title_tokens("ML for Search")


def test_title_similarity_is_one_for_normalization_equivalent_titles():
    assert title_similarity("K-sparse autoencoders", "K-Sparse Autoencoders") == 1.0


def test_title_similarity_measured_reading_wikipedia_pair():
    # The reference asks "...Open-Domain Questions" and the record answers
    # "...Open-Domain Question Answering". Measured 5/7 shared tokens.
    score = title_similarity(
        "Reading Wikipedia to Answer Open-Domain Questions",
        "Reading Wikipedia to Answer Open-Domain Question Answering",
    )
    assert 0.70 <= score < 1.0


def test_title_similarity_is_zero_for_empty_token_sets():
    assert title_similarity("", "Attention Is All You Need") == 0.0
    assert title_similarity("the of a", "Attention Is All You Need") == 0.0


def test_first_author_surname_handles_last_first_and_first_last():
    assert first_author_surname(["Babenko, Artem"]) == "babenko"
    assert first_author_surname(["Artem Babenko"]) == "babenko"
    assert first_author_surname(["Artem Babenko", "Victor Lempitsky"]) == "babenko"


def test_first_author_surname_strips_initials():
    assert first_author_surname(["D. M. Chiorean"]) == "chiorean"
    assert first_author_surname([]) == ""
    assert first_author_surname([""]) == ""


def test_normalize_venue_collapses_crossref_newlines():
    # Crossref returns the publisher's own line wrapping inside container-title.
    wrapped = (
        "Proceedings of the 55th Annual Meeting of the Association for\n"
        "          Computational Linguistics (Volume 1: Long Papers)"
    )
    assert normalize_venue(wrapped) == (
        "proceedings of the 55th annual meeting of the association for computational linguistics "
        "(volume 1: long papers)"
    )


def test_venue_match_share_prefers_tpami_over_cvpr():
    reference = "IEEE Transactions on Pattern Analysis and Machine Intelligence"
    journal = "IEEE Transactions on Pattern Analysis and Machine Intelligence"
    conference = "2012 IEEE Conference on Computer Vision and Pattern Recognition"
    assert venue_match_share(reference, journal) == 1.0
    assert venue_match_share(reference, conference) < 0.5


def test_venue_match_share_is_zero_without_a_reference_venue():
    assert venue_match_share("", "arXiv (Cornell University)") == 0.0


def test_normalize_doi_strips_prefix_and_case():
    assert normalize_doi("https://doi.org/10.1109/TPAMI.2014.2361319") == (
        "10.1109/tpami.2014.2361319"
    )
    assert normalize_doi("doi:10.18653/V1/P17-1171") == "10.18653/v1/p17-1171"
    assert normalize_doi("") == ""


def test_extract_doi_from_plain_and_url_forms():
    assert extract_doi("doi: 10.18653/v1/P17-1171. URL https://example.org") == (
        "10.18653/v1/p17-1171"
    )
    assert extract_doi("See https://doi.org/10.1109/TPAMI.2014.2361319 for details.") == (
        "10.1109/tpami.2014.2361319"
    )
    assert extract_doi("no identifier here") == ""


def test_extract_arxiv_id_from_colon_and_abs_forms():
    assert extract_arxiv_id("arXiv:1710.10723 [cs], October 2017.") == "1710.10723"
    assert extract_arxiv_id("arXiv:1710.10723v2") == "1710.10723"
    assert extract_arxiv_id("CoRR, abs/1308.3432") == "1308.3432"
    assert extract_arxiv_id("http://arxiv.org/abs/1710.10723") == "1710.10723"
    assert extract_arxiv_id("no identifier here") == ""
