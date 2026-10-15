"""Tests for crossref_lookup.py.

The response bodies are trimmed copies of what api.crossref.org actually
returned for these references: unused fields dropped, values untouched, so the
year drift and the list-valued fields are the real ones.
"""

from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from engine.crossref_lookup import (
    NAME,
    SELECT,
    CrossrefLookup,
    build_identifier_url,
    build_url,
    identifier_filter,
    map_item,
    map_items,
)
from engine.identity import ReferenceQuery, select_identity
from engine.metadata_lookup import HttpResult

_TPAMI = "IEEE Transactions on Pattern Analysis and Machine Intelligence"
_CVPR_2012 = "2012 IEEE Conference on Computer Vision and Pattern Recognition"

# Crossref dates this 2015; the reference says 2014. The drift is real and is
# what pins the identity rule's year tolerance from above.
_ITEM = {
    "DOI": "10.1109/TPAMI.2014.2361319",
    "URL": "https://doi.org/10.1109/tpami.2014.2361319",
    "title": ["The inverted multi-index"],
    "author": [
        {"given": "Artem", "family": "Babenko"},
        {"given": "Victor", "family": "Lempitsky"},
    ],
    "issued": {"date-parts": [[2015, 2, 1]]},
    "container-title": [_TPAMI],
    "type": "journal-article",
}

_CVPR_ITEM = {
    "DOI": "10.1109/CVPR.2012.6248014",
    "URL": "https://doi.org/10.1109/cvpr.2012.6248014",
    "title": ["The inverted multi-index"],
    "author": [
        {"given": "Artem", "family": "Babenko"},
        {"given": "Victor", "family": "Lempitsky"},
    ],
    "issued": {"date-parts": [[2012, 6, 16]]},
    "container-title": [_CVPR_2012],
    "type": "proceedings-article",
}

_QUERY = ReferenceQuery(
    title="The inverted multi-index",
    authors=["Artem Babenko", "Victor Lempitsky"],
    year=2014,
    venue=_TPAMI,
)


def _http(body=None, status_code=200, error=""):
    return HttpResult(status_code=status_code, body=body, error=error)


def _search(body, query=None, **kwargs):
    with patch("engine.crossref_lookup.http_get_json", return_value=_http(body)) as call:
        response = CrossrefLookup().search(query or _QUERY, **kwargs)
    return response, call


def _filter_params(url):
    """Return the decoded filter of a request URL, for readability."""
    return parse_qs(urlsplit(url).query)["filter"][0]


# --- Field mapping ------------------------------------------------------------


def test_map_item_reads_the_measured_record():
    candidate = map_item(_ITEM)
    assert candidate.provider == NAME
    assert candidate.record_id == "10.1109/tpami.2014.2361319"
    assert candidate.title == "The inverted multi-index"
    assert candidate.authors == ["Babenko, Artem", "Lempitsky, Victor"]
    assert candidate.year == 2015
    assert candidate.venue == _TPAMI
    assert candidate.kind == "journal-article"
    assert candidate.doi == "10.1109/tpami.2014.2361319"
    assert candidate.is_repository is False


def test_map_item_takes_the_first_non_empty_title():
    # Crossref returns title as a list, and a deposited record can carry a blank
    # first element with the real title behind it.
    assert map_item({**_ITEM, "title": ["", "The inverted multi-index"]}).title == (
        "The inverted multi-index"
    )
    assert map_item({**_ITEM, "title": []}).title == ""
    assert map_item({**_ITEM, "title": "The inverted multi-index"}).title == (
        "The inverted multi-index"
    )


def test_map_item_handles_organisational_and_family_only_authors():
    item = {
        **_ITEM,
        "author": [
            {"family": "Babenko"},
            {"name": "The OpenAlex Consortium"},
            {"given": "NoFamily"},
            "not-a-dict",
        ],
    }
    assert map_item(item).authors == ["Babenko", "The OpenAlex Consortium"]


def test_map_item_handles_every_shape_of_missing_date():
    assert map_item({**_ITEM, "issued": {"date-parts": [[2015]]}}).year == 2015
    assert map_item({**_ITEM, "issued": {"date-parts": []}}).year is None
    assert map_item({**_ITEM, "issued": {"date-parts": [[]]}}).year is None
    assert map_item({**_ITEM, "issued": {}}).year is None
    assert map_item({**_ITEM, "issued": None}).year is None
    assert map_item({**_ITEM, "issued": "2015"}).year is None


def test_map_item_without_any_identifier_is_dropped():
    assert map_item({**_ITEM, "DOI": "", "URL": ""}) is None
    assert map_item({**_ITEM, "DOI": None, "URL": None}) is None
    assert map_item("not-a-dict") is None


def test_map_item_marks_posted_content_as_a_repository_copy():
    item = {**_ITEM, "type": "posted-content", "container-title": []}
    candidate = map_item(item)
    assert candidate.is_repository is True
    assert candidate.venue == ""


def test_map_items_survives_ragged_bodies():
    assert map_items({"message": {"items": [_ITEM, None, {}]}}) == [map_item(_ITEM)]
    assert map_items({"message": {"items": []}}) == []
    assert map_items({"message": {}}) == []
    assert map_items({"message": "nope"}) == []
    assert map_items({}) == []
    assert map_items(None) == []


# --- Query construction -------------------------------------------------------


def test_build_url_asks_for_the_title_and_the_first_author_surname():
    params = parse_qs(urlsplit(build_url(_QUERY, 10)).query)
    query = params["query.bibliographic"][0]
    assert "The inverted multi-index" in query
    assert "babenko" in query
    assert params["rows"] == ["10"]


def test_build_url_does_not_quote_the_query():
    # Quotation is Google Scholar's phrase syntax; Crossref would match the
    # characters themselves.
    params = parse_qs(urlsplit(build_url(_QUERY, 10)).query)
    assert '"' not in params["query.bibliographic"][0]


def test_build_url_omits_the_surname_when_the_reference_has_no_authors():
    params = parse_qs(urlsplit(build_url(ReferenceQuery(title="K-sparse autoencoders"), 10)).query)
    assert params["query.bibliographic"] == ["K-sparse autoencoders"]


def test_build_identifier_url_asks_by_doi():
    params = parse_qs(urlsplit(build_identifier_url(
        ReferenceQuery(title="The inverted multi-index", doi="10.1109/TPAMI.2014.2361319"), 10
    )).query)
    assert params["filter"] == ["doi:10.1109/tpami.2014.2361319"]
    assert params["rows"] == ["10"]
    assert params["select"] == [SELECT]


def test_identifier_filter_is_empty_for_an_arxiv_doi():
    # arXiv's DOIs are registered with DataCite, not Crossref. Measured:
    # ``filter=doi:10.48550/arxiv.1502.03167`` answers 200 with
    # ``total-results: 0`` -- so asking would spend a request on an answer that
    # cannot come, and the title query is the only one worth making.
    assert identifier_filter(ReferenceQuery(
        title="Batch Normalization", doi="10.48550/arXiv.1502.03167"
    )) == ""
    assert identifier_filter(ReferenceQuery(
        title="Batch Normalization", arxiv_id="1502.03167"
    )) == ""


def test_identifier_filter_is_empty_without_a_doi():
    assert identifier_filter(ReferenceQuery(title="K-sparse autoencoders")) == ""
    assert identifier_filter(ReferenceQuery(title="x", doi="10.1234/a|b")) == ""


# --- Transport ----------------------------------------------------------------


def test_search_maps_a_body_onto_candidates():
    response, call = _search({"message": {"items": [_ITEM, _CVPR_ITEM]}})
    assert response.status == "ok"
    assert [candidate.record_id for candidate in response.candidates] == [
        "10.1109/tpami.2014.2361319",
        "10.1109/cvpr.2012.6248014",
    ]
    assert call.call_args.args[0].startswith("https://api.crossref.org/works?")


def test_search_passes_the_limit_and_timeout_through():
    _, call = _search({"message": {"items": []}}, limit=4, timeout_seconds=3.5)
    assert "rows=4" in call.call_args.args[0]
    assert call.call_args.kwargs["timeout_seconds"] == 3.5


def test_search_without_a_title_does_not_make_a_request():
    with patch("engine.crossref_lookup.http_get_json") as call:
        response = CrossrefLookup().search(ReferenceQuery(authors=["Artem Babenko"]))
    assert response.status == "ok"
    assert response.candidates == []
    assert call.called is False


def test_search_asks_a_reference_with_a_doi_by_doi():
    response, call = _search(
        {"message": {"items": [_ITEM]}},
        query=ReferenceQuery(title="The inverted multi-index", doi="10.1109/tpami.2014.2361319"),
    )
    assert [candidate.record_id for candidate in response.candidates] == [
        "10.1109/tpami.2014.2361319"
    ]
    assert call.call_count == 1
    assert _filter_params(call.call_args.args[0]) == "doi:10.1109/tpami.2014.2361319"


def test_search_does_not_ask_crossref_for_an_arxiv_doi():
    # The identifier picks nothing here, so the one request is the title query:
    # a DataCite DOI is never spent against the wrong registration agency.
    response, call = _search(
        {"message": {"items": [_ITEM]}},
        query=ReferenceQuery(title="The inverted multi-index", doi="10.48550/arxiv.1502.03167"),
    )
    assert response.status == "ok"
    assert call.call_count == 1
    assert "filter" not in parse_qs(urlsplit(call.call_args.args[0]).query)


def test_search_falls_back_to_the_title_when_the_identifier_finds_nothing():
    with patch(
        "engine.crossref_lookup.http_get_json",
        side_effect=[
            _http({"message": {"items": [], "total-results": 0}}),
            _http({"message": {"items": [_ITEM]}}),
        ],
    ) as call:
        response = CrossrefLookup().search(ReferenceQuery(
            title="The inverted multi-index",
            authors=["Artem Babenko"],
            doi="10.9999/not-indexed",
        ))
    assert [candidate.record_id for candidate in response.candidates] == [
        "10.1109/tpami.2014.2361319"
    ]
    assert call.call_count == 2
    assert _filter_params(call.call_args_list[0].args[0]) == "doi:10.9999/not-indexed"
    assert "query.bibliographic" in parse_qs(urlsplit(call.call_args_list[1].args[0]).query)


def test_search_does_not_fall_back_when_the_identifier_request_fails():
    with patch(
        "engine.crossref_lookup.http_get_json",
        return_value=_http(status_code=429, error="HTTP 429 Too Many Requests"),
    ) as call:
        response = CrossrefLookup().search(ReferenceQuery(
            title="The inverted multi-index", doi="10.9999/not-indexed"
        ))
    assert response.status == "rate_limited"
    assert call.call_count == 1


def test_search_maps_a_throttle():
    with patch(
        "engine.crossref_lookup.http_get_json",
        return_value=_http(status_code=429, error="HTTP 429 Too Many Requests"),
    ):
        response = CrossrefLookup().search(_QUERY)
    assert response.status == "rate_limited"
    assert response.error_code == "CROSSREF_RATE_LIMITED"


def test_search_treats_a_404_as_an_empty_answer_not_a_failure():
    with patch(
        "engine.crossref_lookup.http_get_json",
        return_value=_http(status_code=404, error="HTTP 404 Not Found"),
    ):
        response = CrossrefLookup().search(_QUERY)
    assert response.status == "ok"
    assert response.candidates == []


def test_search_maps_a_server_error():
    with patch(
        "engine.crossref_lookup.http_get_json",
        return_value=_http(status_code=503, error="HTTP 503 Service Unavailable"),
    ):
        response = CrossrefLookup().search(_QUERY)
    assert response.status == "failed"
    assert response.error_code == "CROSSREF_HTTP_503"


def test_search_maps_a_transport_failure():
    with patch(
        "engine.crossref_lookup.http_get_json",
        return_value=_http(status_code=0, error="request failed: timed out"),
    ):
        response = CrossrefLookup().search(_QUERY)
    assert response.status == "failed"
    assert response.error_code == "CROSSREF_TRANSPORT"


def test_search_maps_a_body_that_could_not_be_read():
    with patch(
        "engine.crossref_lookup.http_get_json",
        return_value=_http(status_code=200, error="response was not JSON: boom"),
    ):
        response = CrossrefLookup().search(_QUERY)
    assert response.status == "failed"
    assert response.error_code == "CROSSREF_UNREADABLE_BODY"


# --- Against the identity rule ------------------------------------------------


def test_the_cited_journal_version_is_selected_over_the_conference_twin():
    # Both records come back with the same title and authors. The conference
    # version is two years out, so the year veto drops it; the journal version,
    # one year out from Crossref's stamp, survives.
    response, _ = _search({"message": {"items": [_CVPR_ITEM, _ITEM]}})
    decision = select_identity(_QUERY, response.candidates)
    assert decision.status == "found"
    assert decision.selected is not None
    assert decision.selected.record_id == "10.1109/tpami.2014.2361319"
    assert [item.candidate.record_id for item in decision.rejected] == [
        "10.1109/cvpr.2012.6248014"
    ]
