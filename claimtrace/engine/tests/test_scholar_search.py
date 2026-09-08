"""Tests for scholar_search.py."""

from unittest.mock import patch

from engine.scholar_search import (
    ScholarSearchOutcome,
    search_scholar,
)


class _FakePub:
    def __init__(self, title, authors, year, venue, url):
        self.bib = {"title": title, "author": authors, "pub_year": year, "venue": venue}
        self.pub_url = url


def _search_returning(*pubs):
    """Patch scholarly.search_pubs to return the given publications."""

    def _fake(query, **kwargs):
        return list(pubs)

    return patch("engine.scholar_search.scholarly.search_pubs", side_effect=_fake)


def test_search_found_for_single_hit():
    pub = _FakePub("Attention Is All You Need", ["A Vaswani"], "2017", "NeurIPS", "http://x")
    with _search_returning(pub):
        outcome = search_scholar("Attention Is All You Need", ["Vaswani, Ashish"], 2017)

    assert outcome.status == "found"
    assert len(outcome.results) == 1
    assert outcome.results[0].title == "Attention Is All You Need"
    assert outcome.results[0].year == 2017
    assert outcome.results[0].venue == "NeurIPS"


def test_search_ambiguous_for_multiple_hits():
    pubs = [
        _FakePub("Title One", ["A Smith"], "2020", "Venue", "http://1"),
        _FakePub("Title Two", ["B Jones"], "2021", "Venue", "http://2"),
    ]
    with _search_returning(*pubs):
        outcome = search_scholar("Some Title", ["Smith, A"], None)

    assert outcome.status == "ambiguous"
    assert len(outcome.results) == 2


def test_search_not_found_for_no_hits():
    with _search_returning():
        outcome = search_scholar("Nonexistent Title", ["Nobody"], 1999)

    assert outcome.status == "not_found"
    assert outcome.results == []


def test_search_failed_on_exception():
    def _raise(query, **kwargs):
        raise RuntimeError("blocked by captcha")

    with patch("engine.scholar_search.scholarly.search_pubs", side_effect=_raise):
        outcome = search_scholar("Any Title", ["Smith, A"], None)

    assert outcome.status == "failed"
    assert "blocked" in outcome.error


def test_search_failed_when_title_empty():
    outcome = search_scholar("", ["Smith, A"], 2020)
    assert outcome.status == "failed"
    assert "title" in outcome.error.lower()


def test_search_handles_dict_publication():
    # scholarly 1.7.x returns plain dicts (not objects); verify both work.
    pub = {
        "bib": {"title": "Attention Is All You Need", "author": ["A Vaswani"],
                "pub_year": "2017", "venue": "NeurIPS"},
        "pub_url": "http://x",
    }
    with _search_returning(pub):
        outcome = search_scholar("Attention Is All You Need", ["Vaswani, Ashish"], 2017)

    assert outcome.status == "found"
    assert outcome.results[0].title == "Attention Is All You Need"
    assert outcome.results[0].year == 2017


def test_build_query_includes_surname():
    from engine.scholar_search import _build_query

    assert _build_query("My Title", ["Vaswani, Ashish"]) == '"My Title" Vaswani'
    assert _build_query("My Title", None) == '"My Title"'
