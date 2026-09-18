"""Tests for identity.py.

Every value here is a measurement, not an invention: the titles, venues, years,
and record identifiers are the ones two live providers actually returned for the
references in ``backend/uploads/parsed/``. Nothing in this file touches the
network, so the rule can be re-checked without re-querying.
"""

from engine.identity import (
    IdentityDecision,
    PublicationCandidate,
    ReferenceQuery,
    select_identity,
)
from engine.title_matching import first_author_surname, normalize_title

_TPAMI = "IEEE Transactions on Pattern Analysis and Machine Intelligence"
_CVPR_2012 = "2012 IEEE Conference on Computer Vision and Pattern Recognition"
_ACL_2017 = (
    "Proceedings of the 55th Annual Meeting of the Association for "
    "Computational Linguistics (Volume 1: Long Papers)"
)


def _record(**overrides) -> PublicationCandidate:
    fields = {
        "provider": "openalex",
        "record_id": "W1",
        "title": "",
        "authors": [],
        "year": None,
        "venue": "",
        "kind": "journal-article",
        "doi": "",
        "arxiv_id": "",
        "url": "",
        "is_repository": False,
    }
    fields.update(overrides)
    return PublicationCandidate(**fields)


# --- The spoof, measured live -------------------------------------------------
# Querying "Attention Is All You Need" returns records registered in 2025 by an
# unrelated organisation, with the real author list copied verbatim, a
# ``posted-content`` type, and no container title at all. Against a 2017
# reference they agree on the title exactly and on the first author exactly.

_ATTENTION_AUTHORS = ["Ashish Vaswani", "Noam Shazeer", "Niki Parmar", "Jakob Uszkoreit"]


def _attention_reference() -> ReferenceQuery:
    return ReferenceQuery(
        title="Attention is all you need",
        authors=_ATTENTION_AUTHORS,
        year=2017,
        venue="Advances in Neural Information Processing Systems",
    )


def _spoof(record_id: str) -> PublicationCandidate:
    return _record(
        provider="crossref",
        record_id=record_id,
        title="Attention Is All You Need",
        authors=_ATTENTION_AUTHORS,
        year=2025,
        venue="",
        kind="posted-content",
        doi=f"10.65215/{record_id}",
    )


def test_live_spoof_is_not_found():
    records = [_spoof(f"2025-{index}") for index in range(4)]
    decision = select_identity(_attention_reference(), records)
    assert decision.status == "not_found"
    assert decision.selected is None
    assert len(decision.rejected) == 4


def test_the_venue_requirement_alone_rejects_a_perfect_title_match():
    # One record, nothing competing: the strongest possible case for a weighted
    # rule, and it still must not be reported as the cited work.
    query = _attention_reference()
    record = _spoof("2025-1")
    assert normalize_title(record.title) == normalize_title(query.title)
    assert first_author_surname(record.authors) == first_author_surname(query.authors)
    decision = select_identity(query, [record])
    assert decision.status == "not_found"
    assert [item.reason for item in decision.rejected] == ["no venue"]


def test_the_year_veto_alone_rejects_a_perfect_title_match():
    query = _attention_reference()
    record = _spoof("2025-1")
    record.venue = "arXiv"
    decision = select_identity(query, [record])
    assert decision.status == "not_found"
    assert [item.reason for item in decision.rejected] == ["year disagrees"]


# --- The identifier pre-pass --------------------------------------------------


def test_matching_doi_is_found_despite_a_year_drift_and_no_venue():
    # Crossref dates this DOI 2015 and OpenAlex dates it 2014, against a
    # reference that says 2014. A DOI is the work, not evidence about it.
    query = ReferenceQuery(doi="10.1109/TPAMI.2014.2361319")
    record = _record(
        record_id="10.1109/tpami.2014.2361319",
        title="The inverted multi-index",
        authors=["Artem Babenko", "Victor Lempitsky"],
        year=2015,
        venue="",
        doi="https://doi.org/10.1109/TPAMI.2014.2361319",
    )
    decision = select_identity(query, [record])
    assert decision.status == "found"
    assert decision.rule == "doi"
    assert decision.selected is record


def test_a_doi_both_providers_indexed_twice_is_still_settled_by_the_identifier():
    # Measured, from the annotated benchmark: this reference carries its own
    # DOI, and both providers returned a record under it. Requiring exactly one
    # hit sent the reference down the title path, where it was settled by a
    # weaker rule than the identifier already in hand. A shared DOI makes the
    # two one work, so the count is not evidence against the match.
    query = ReferenceQuery(
        title="Reading Wikipedia to Answer Open-Domain Questions",
        authors=["Danqi Chen"],
        year=2017,
        doi="10.18653/v1/P17-1171",
    )
    openalex = _record(
        provider="openalex",
        record_id="W2963472678",
        title="Reading Wikipedia to Answer Open-Domain Questions",
        authors=["Danqi Chen", "Adam Fisch"],
        year=2017,
        venue=_ACL_2017,
        doi="https://doi.org/10.18653/v1/P17-1171",
    )
    crossref = _record(
        provider="crossref",
        record_id="10.18653/v1/p17-1171",
        title="Reading Wikipedia to Answer Open-Domain Questions",
        authors=["Chen, Danqi", "Fisch, Adam"],
        year=2017,
        venue=_ACL_2017,
        kind="proceedings-article",
        doi="10.18653/v1/p17-1171",
    )
    decision = select_identity(query, [openalex, crossref])
    assert decision.status == "found"
    assert decision.rule == "doi"
    assert decision.selected is crossref


def test_matching_doi_does_not_rescue_a_non_publication():
    query = ReferenceQuery(doi="10.1109/TPAMI.2014.2361319", title="The inverted multi-index")
    record = _record(
        record_id="10.1109/tpami.2014.2361319",
        title="The inverted multi-index",
        year=2014,
        venue=_TPAMI,
        kind="component",
        doi="10.1109/TPAMI.2014.2361319",
    )
    decision = select_identity(query, [record])
    assert decision.status == "not_found"
    assert [item.reason for item in decision.rejected] == ["not a publication type"]


def test_arxiv_identifier_in_a_datacite_doi_is_matched():
    # OpenAlex reports a preprint's DOI as 10.48550/arXiv.<id>, so the
    # identifier has to be readable out of the DOI rather than off a field.
    query = ReferenceQuery(arxiv_id="1710.10723", title="Something else entirely")
    record = _record(
        record_id="W2963472678",
        title="Something else entirely",
        year=2017,
        venue="arXiv",
        kind="preprint",
        doi="10.48550/arXiv.1710.10723",
        is_repository=True,
    )
    decision = select_identity(query, [record])
    assert decision.status == "found"
    assert decision.rule == "arxiv"


def test_a_doi_that_matches_no_record_is_not_found():
    # A reference reduced to its identifier: the title path is unavailable, so
    # the identifier has to resolve it or nothing can.
    query = ReferenceQuery(doi="10.1109/TPAMI.2014.2361319")
    record = _record(record_id="W2", title="The inverted multi-index", year=2014, venue=_TPAMI)
    decision = select_identity(query, [record])
    assert decision.status == "not_found"
    assert decision.rule == "identifier"


# --- The year tolerance, pinned from both sides -------------------------------


def test_tolerance_admits_a_one_year_drift():
    # A tolerance of 0 would reject this, which is the correct record.
    query = ReferenceQuery(title="The inverted multi-index", year=2014, venue=_TPAMI)
    record = _record(record_id="W3", title="The inverted multi-index", year=2015, venue=_TPAMI)
    assert select_identity(query, [record]).status == "found"


def test_tolerance_rejects_a_two_year_drift():
    # A tolerance of 2 would admit the superseded conference version.
    query = ReferenceQuery(title="The inverted multi-index", year=2014, venue=_TPAMI)
    record = _record(
        record_id="W4", title="The inverted multi-index", year=2012, venue=_CVPR_2012
    )
    decision = select_identity(query, [record])
    assert decision.status == "not_found"
    assert [item.reason for item in decision.rejected] == ["year disagrees"]


def test_preprint_is_eligible_and_venue_never_vetoes():
    # The correct record for this reference is an OpenAlex preprint dated one
    # year before the reference, whose venue is a repository. Rejecting either
    # would remove the reason to query OpenAlex at all.
    query = ReferenceQuery(
        title="K-sparse autoencoders",
        authors=["Alireza Makhzani", "Brendan Frey"],
        year=2014,
        venue="International Conference on Learning Representations",
    )
    record = _record(
        record_id="W5",
        title="K-sparse autoencoders",
        authors=["Alireza Makhzani", "Brendan Frey"],
        year=2013,
        venue="arXiv",
        kind="preprint",
        is_repository=True,
    )
    decision = select_identity(query, [record])
    assert decision.status == "found"
    assert decision.selected is record


# --- Same-work collapse and the venue tie-break -------------------------------


def _duplicate_arxiv_record() -> PublicationCandidate:
    return _record(
        provider="openalex",
        record_id="W6",
        title="Winner-take-all autoencoders",
        authors=["Alireza Makhzani", "Brendan Frey"],
        year=2015,
        venue="arXiv",
        kind="preprint",
        is_repository=True,
    )


def test_duplicate_records_for_one_work_are_collapsed():
    # OpenAlex returned this one twice, byte-identical: two distinct records
    # carrying the same fields, not one record passed twice.
    query = ReferenceQuery(
        title="Winner-take-all autoencoders",
        authors=["Alireza Makhzani", "Brendan Frey"],
        year=2015,
        venue="Advances in Neural Information Processing Systems",
    )
    decision = select_identity(query, [_duplicate_arxiv_record(), _duplicate_arxiv_record()])
    assert decision.status == "found"
    assert decision.rule == "exact-title+dedup"
    assert decision.selected.record_id == "W6"
    assert len(decision.candidates) == 1


def test_collapse_prefers_a_published_record_over_a_repository_copy():
    query = ReferenceQuery(
        title="Winner-take-all autoencoders",
        authors=["Alireza Makhzani", "Brendan Frey"],
        year=2015,
        venue="",
    )
    preprint = _record(
        provider="openalex",
        record_id="W7",
        title="Winner-take-all autoencoders",
        authors=["Alireza Makhzani", "Brendan Frey"],
        year=2015,
        venue="arXiv (Cornell University)",
        kind="preprint",
        is_repository=True,
    )
    published = _record(
        provider="crossref",
        record_id="10.5555/2969239.2969354",
        title="Winner-take-all autoencoders",
        authors=["Alireza Makhzani", "Brendan Frey"],
        year=2015,
        venue="Advances in Neural Information Processing Systems",
        kind="proceedings-article",
        doi="10.5555/2969239.2969354",
    )
    decision = select_identity(query, [preprint, published])
    assert decision.status == "found"
    assert decision.rule == "exact-title+dedup"
    assert decision.selected is published


def test_collapse_does_not_fold_two_years_of_the_same_title():
    # A journal article and its earlier conference version are different works
    # with different DOIs. Folding them would let the wrong one be selected.
    query = ReferenceQuery(
        title="The inverted multi-index",
        authors=["Artem Babenko", "Victor Lempitsky"],
        year=2012,
        venue="",
    )
    conference = _record(
        record_id="W8",
        title="The inverted multi-index",
        authors=["Artem Babenko", "Victor Lempitsky"],
        year=2012,
        venue=_CVPR_2012,
        kind="proceedings-article",
    )
    journal = _record(
        record_id="W9",
        title="The inverted multi-index",
        authors=["Artem Babenko", "Victor Lempitsky"],
        year=2011,
        venue=_TPAMI,
    )
    decision = select_identity(query, [conference, journal])
    assert decision.status == "ambiguous"
    assert len(decision.candidates) == 2


def test_one_doi_is_one_work_even_when_the_providers_disagree_on_the_year():
    # Measured, from the annotated benchmark. Both providers returned the same
    # DOI for this reference; OpenAlex dated it 2014 and Crossref 2015. The
    # year pair therefore did not agree, the two records landed in different
    # groups, and the venue tie-break then compared a record with itself and
    # abstained -- the reference came back ambiguous between one work and the
    # same work. A shared DOI is the work, so the year cannot separate them.
    query = ReferenceQuery(
        title="The inverted multi-index",
        authors=["Artem Babenko", "Victor Lempitsky"],
        year=2014,
        venue=_TPAMI,
    )
    openalex = _record(
        provider="openalex",
        record_id="W22",
        title="The inverted multi-index",
        authors=["Artem Babenko", "Victor Lempitsky"],
        year=2014,
        venue=_TPAMI,
        doi="10.1109/TPAMI.2014.2361319",
    )
    crossref = _record(
        provider="crossref",
        record_id="10.1109/tpami.2014.2361319",
        title="The Inverted Multi-Index",
        authors=["Babenko, Artem", "Lempitsky, Victor"],
        year=2015,
        venue=_TPAMI,
        kind="journal-article",
        doi="10.1109/TPAMI.2014.2361319",
    )
    decision = select_identity(query, [openalex, crossref])
    assert decision.status == "found"
    assert decision.rule == "exact-title+dedup"
    assert decision.selected.doi == "10.1109/TPAMI.2014.2361319"


def test_the_conference_version_shares_no_doi_and_is_still_kept_separate():
    # The other side of the same rule: the CVPR version shares the title, the
    # first author and the reference's venue prefix, and differs in the one
    # field that identifies a work. Merging on anything but the DOI would fold
    # it in.
    query = ReferenceQuery(
        title="The inverted multi-index",
        authors=["Artem Babenko", "Victor Lempitsky"],
        year=None,
        venue=_TPAMI,
    )
    conference = _record(
        record_id="10.1109/CVPR.2012.6248038",
        title="The inverted multi-index",
        authors=["Artem Babenko", "Victor Lempitsky"],
        year=2012,
        venue=_CVPR_2012,
        kind="proceedings-article",
        doi="10.1109/CVPR.2012.6248038",
    )
    journal = _record(
        record_id="10.1109/TPAMI.2014.2361319",
        title="The inverted multi-index",
        authors=["Artem Babenko", "Victor Lempitsky"],
        year=2014,
        venue=_TPAMI,
        doi="10.1109/TPAMI.2014.2361319",
    )
    decision = select_identity(query, [conference, journal])
    assert decision.status == "found"
    assert decision.selected.doi == "10.1109/TPAMI.2014.2361319"
    assert [item.record_id for item in decision.candidates] == ["10.1109/CVPR.2012.6248038"]


def test_venue_selects_the_cited_version_when_the_year_is_unknown():
    # The reference names the journal, so the conference twin must lose even
    # though it outranks the journal in the raw provider ordering.
    query = ReferenceQuery(
        title="The inverted multi-index",
        authors=["Artem Babenko", "Victor Lempitsky"],
        year=None,
        venue=_TPAMI,
    )
    conference = _record(
        record_id="W10",
        title="The inverted multi-index",
        authors=["Artem Babenko", "Victor Lempitsky"],
        year=2012,
        venue=_CVPR_2012,
        kind="proceedings-article",
    )
    journal = _record(
        record_id="W11",
        title="The inverted multi-index",
        authors=["Artem Babenko", "Victor Lempitsky"],
        year=2014,
        venue=_TPAMI,
    )
    decision = select_identity(query, [conference, journal])
    assert decision.status == "found"
    assert decision.rule == "exact-title+venue"
    assert decision.selected is journal
    # The overruled candidate stays visible, so the choice can be reviewed.
    assert [item.record_id for item in decision.candidates] == ["W10"]


def test_equal_venue_shares_leave_the_decision_ambiguous():
    query = ReferenceQuery(
        title="The inverted multi-index",
        authors=["Artem Babenko", "Victor Lempitsky"],
        year=None,
        venue="arXiv",
    )
    first = _record(record_id="W12", title="The inverted multi-index", year=2012, venue="arXiv")
    second = _record(record_id="W13", title="The inverted multi-index", year=2014, venue="arXiv")
    decision = select_identity(query, [first, second])
    assert decision.status == "ambiguous"
    assert decision.rule == "exact-title"
    assert {item.record_id for item in decision.candidates} == {"W12", "W13"}


def test_a_ligature_in_the_reference_still_matches_exactly():
    # PDF text extraction leaves the fi ligature in the reference list; NFKC
    # folds it in the record comparison, not by hand.
    query = ReferenceQuery(
        title="Trading representation for accuracy: ﬁxed-length embeddings",
        year=2018,
        venue=_ACL_2017,
    )
    record = _record(
        record_id="W14",
        title="Trading Representation for Accuracy: Fixed-Length Embeddings",
        year=2018,
        venue=_ACL_2017,
    )
    decision = select_identity(query, [record])
    assert decision.status == "found"
    assert decision.rule == "exact-title"


# --- When nothing matched exactly ----------------------------------------------
# There is no fuzzy tier: the thresholds one would need never decided a case on
# the annotated set, so a title that merely resembles the reference goes to a
# person however well the authors and the year agree. What is left is the
# question the last step asks instead, which has no threshold in it.


def _near_miss_pair() -> tuple[ReferenceQuery, PublicationCandidate]:
    query = ReferenceQuery(
        title="Reading Wikipedia to Answer Open-Domain Questions",
        authors=["Danqi Chen"],
        year=2017,
        venue=_ACL_2017,
    )
    record = _record(
        record_id="W15",
        title="Reading Wikipedia to Answer Open-Domain Question Answering",
        authors=["Danqi Chen"],
        year=2017,
        venue=_ACL_2017,
    )
    return query, record


def test_a_near_miss_title_is_offered_for_review_rather_than_selected():
    query, record = _near_miss_pair()
    decision = select_identity(query, [record])
    assert decision.status == "ambiguous"
    assert decision.rule == "title-overlap"
    assert decision.candidates == [record]


def test_the_closest_records_are_the_ones_offered():
    query, record = _near_miss_pair()
    # All four share exactly one informative token, so they tie on overlap and
    # the order among them is the order they arrived in. Only the nearest three
    # are shown, since a caller choosing between more than that is not reading
    # them anyway.
    extras = [
        _record(record_id=f"W2{index}", title=f"Reading in the field of {topic}",
                year=2017, venue=_ACL_2017)
        for index, topic in enumerate(("law", "medicine", "education", "commerce"))
    ]
    decision = select_identity(query, [*extras, record])
    assert decision.status == "ambiguous"
    assert decision.candidates == [record, extras[0], extras[1]]


# --- Guards -------------------------------------------------------------------


def test_a_reference_with_nothing_to_match_on_is_not_found():
    decision = select_identity(ReferenceQuery(), [])
    assert decision.status == "not_found"
    assert "neither" in decision.reason


def test_no_returned_records_is_not_found():
    decision = select_identity(ReferenceQuery(title="The inverted multi-index"), [])
    assert decision.status == "not_found"
    assert "no records" in decision.reason


def test_rejections_are_reported_by_cause():
    query = ReferenceQuery(title="The inverted multi-index", year=2014, venue=_TPAMI)
    records = [
        _record(record_id="W17", title="The inverted multi-index", year=2012, venue=_TPAMI),
        _record(record_id="W18", title="The inverted multi-index", year=2010, venue=_TPAMI),
        _record(record_id="W19", title="The inverted multi-index", year=2014, venue=""),
    ]
    decision = select_identity(query, records)
    assert decision.status == "not_found"
    assert "3 of 3 records were ineligible" in decision.reason
    assert "2 year disagrees" in decision.reason
    assert "1 no venue" in decision.reason


def test_records_sharing_no_title_token_are_not_found_not_ambiguous():
    # Nothing here could be the cited work, so presenting the caller with a
    # choice between them would be a false one.
    query = ReferenceQuery(title="An unrelated work on something else", year=2014, venue=_TPAMI)
    record = _record(record_id="W21", title="The inverted multi-index", year=2014, venue=_TPAMI)
    decision = select_identity(query, [record])
    assert decision.status == "not_found"
    assert decision.rule == "title-overlap"


def test_select_identity_never_raises_on_ragged_input():
    # Providers are not obliged to fill every field, and a missing year or an
    # empty author list must not be an error path.
    decision = select_identity(ReferenceQuery(title="x"), [_record(record_id="W20", title="x")])
    assert isinstance(decision, IdentityDecision)
