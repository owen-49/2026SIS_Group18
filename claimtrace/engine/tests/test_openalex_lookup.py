"""Tests for openalex_lookup.py.

The response bodies are trimmed copies of what api.openalex.org actually
returned for these references, including the field shapes that make this
provider's mapping easy to get wrong: a null ``source`` with the venue only in
``raw_source_name``, and a hijacked record whose ``locations[]`` carries venues
its primary location does not.
"""

from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from engine.identity import ReferenceQuery, select_identity
from engine.metadata_lookup import HttpResult
from engine.openalex_lookup import (
    NAME,
    OpenAlexLookup,
    build_identifier_url,
    build_url,
    identifier_filter,
    map_item,
    map_items,
)
from engine.title_matching import extract_arxiv_id

_ACL_2017 = (
    "Proceedings of the 55th Annual Meeting of the Association for "
    "Computational Linguistics (Volume 1: Long Papers)"
)

# The correct record for this reference. ``source`` is null, so a mapping that
# reads only ``source.display_name`` sees no venue and the identity rule rejects
# a correct answer for having none.
_ACL_ITEM = {
    "id": "https://openalex.org/W2963472678",
    "doi": "https://doi.org/10.18653/v1/P17-1171",
    "title": "Reading Wikipedia to Answer Open-Domain Questions",
    "publication_year": 2017,
    "type": "article",
    "authorships": [
        {"author": {"display_name": "Danqi Chen"}},
        {"author": {"display_name": "Adam Fisch"}},
    ],
    "primary_location": {
        "source": None,
        "raw_source_name": _ACL_2017,
        "landing_page_url": "https://aclanthology.org/P17-1171",
    },
}

_PREPRINT_ITEM = {
    "id": "https://openalex.org/W2963472679",
    "doi": "https://doi.org/10.48550/arXiv.1312.5663",
    "title": "K-sparse autoencoders",
    "publication_year": 2013,
    "type": "preprint",
    "authorships": [{"author": {"display_name": "Alireza Makhzani"}}],
    "primary_location": {
        "source": {"display_name": "arXiv", "type": "repository"},
        "raw_source_name": "arXiv",
        "landing_page_url": "https://arxiv.org/abs/1312.5663",
    },
}

# The fabricated record. Its primary location carries no venue at all, but three
# arXiv entries sit in ``locations[]``.
_HIJACKED_ITEM = {
    "id": "https://openalex.org/W7123456789",
    "doi": "https://doi.org/10.65215/xyz",
    "title": "Attention Is All You Need",
    "publication_year": 2025,
    "type": "preprint",
    "authorships": [{"author": {"display_name": "Ashish Vaswani"}}],
    "primary_location": {"source": None, "raw_source_name": None, "landing_page_url": None},
    "locations": [
        {"source": {"display_name": "arXiv", "type": "repository"}, "raw_source_name": "arXiv"},
        {"source": {"display_name": "arXiv", "type": "repository"}, "raw_source_name": "arXiv"},
        {"source": {"display_name": "arXiv", "type": "repository"}, "raw_source_name": "arXiv"},
    ],
}


def _http(body=None, status_code=200, error=""):
    return HttpResult(status_code=status_code, body=body, error=error)


def _search(body, query=None, **kwargs):
    with patch("engine.openalex_lookup.http_get_json", return_value=_http(body)) as call:
        response = OpenAlexLookup().search(query or ReferenceQuery(title="x"), **kwargs)
    return response, call


# --- Field mapping ------------------------------------------------------------


def test_map_item_reads_a_logical_identifier_from_the_openalex_url():
    candidate = map_item(_ACL_ITEM)
    assert candidate.provider == NAME
    assert candidate.record_id == "W2963472678"
    assert candidate.title == "Reading Wikipedia to Answer Open-Domain Questions"
    assert candidate.authors == ["Danqi Chen", "Adam Fisch"]
    assert candidate.year == 2017
    assert candidate.doi == "10.18653/v1/p17-1171"
    assert candidate.url == "https://aclanthology.org/P17-1171"


def test_map_item_falls_back_to_raw_source_name_when_source_is_null():
    # Without this fallback the record has no venue, and the identity rule
    # rejects it for that. The reference is then reported as unresolvable while
    # the correct record was sitting in the response.
    assert map_item(_ACL_ITEM).venue == _ACL_2017


def test_map_item_prefers_the_source_display_name_when_both_are_present():
    item = {
        **_ACL_ITEM,
        "primary_location": {
            "source": {"display_name": "Association for Computational Linguistics"},
            "raw_source_name": "an older spelling of the proceedings",
        },
    }
    assert map_item(item).venue == "Association for Computational Linguistics"


def test_map_item_never_reads_a_venue_out_of_locations():
    # The hijacked record has three arXiv entries in locations[] and nothing in
    # its primary location. Reading locations[] would hand it a venue and let it
    # past the filter that rejects it.
    candidate = map_item(_HIJACKED_ITEM)
    assert candidate.venue == ""
    assert candidate.year == 2025


def test_map_item_marks_a_repository_primary_location():
    candidate = map_item(_PREPRINT_ITEM)
    assert candidate.is_repository is True
    assert candidate.kind == "preprint"
    assert map_item(_ACL_ITEM).is_repository is False


def test_map_item_exposes_the_arxiv_identifier_of_a_preprint():
    # The identifier is only in the DOI and the landing page, so whichever of
    # the two the identity rule reads has to yield the same id.
    candidate = map_item(_PREPRINT_ITEM)
    assert extract_arxiv_id(candidate.doi) == "1312.5663"
    assert extract_arxiv_id(candidate.url) == "1312.5663"


def test_map_item_flags_paratext_regardless_of_its_type():
    assert map_item({**_ACL_ITEM, "is_paratext": True}).kind == "paratext"
    assert map_item({**_ACL_ITEM, "is_paratext": False}).kind == "article"


def test_map_item_reads_the_newer_display_name_when_title_is_gone():
    item = {**_ACL_ITEM, "title": None, "display_name": "Reading Wikipedia"}
    assert map_item(item).title == "Reading Wikipedia"


def test_map_item_without_any_identifier_is_dropped():
    assert map_item({**_ACL_ITEM, "id": "", "doi": ""}) is None
    assert map_item({**_ACL_ITEM, "id": None, "doi": None}) is None
    assert map_item("not-a-dict") is None


def test_map_item_tolerates_a_malformed_primary_location():
    assert map_item({**_ACL_ITEM, "primary_location": None}).venue == ""
    assert map_item({**_ACL_ITEM, "primary_location": "nope"}).venue == ""
    assert map_item({**_ACL_ITEM, "primary_location": {"source": "nope"}}).venue == ""


def test_map_item_tolerates_a_malformed_publication_year():
    assert map_item({**_ACL_ITEM, "publication_year": None}).year is None
    assert map_item({**_ACL_ITEM, "publication_year": "2017"}).year is None


def test_map_items_survives_ragged_bodies():
    assert map_items({"results": [_ACL_ITEM, None, {}]}) == [map_item(_ACL_ITEM)]
    assert map_items({"results": []}) == []
    assert map_items({"results": "nope"}) == []
    assert map_items({}) == []
    assert map_items(None) == []


# --- Query construction -------------------------------------------------------


def test_build_url_asks_by_title_and_leaves_the_author_out():
    # Measured: adding the author name pushes the correct record out of the
    # first six results. Crossref wants the surname; this provider must not.
    params = parse_qs(urlsplit(build_url(ReferenceQuery(
        title="The inverted multi-index", authors=["Artem Babenko"]
    ), 10)).query)
    assert params["filter"] == ["title.search:The inverted multi-index"]
    assert params["per-page"] == ["10"]
    assert "Babenko" not in params["filter"][0]
    assert "mailto" not in params


def test_build_url_does_not_quote_the_query():
    params = parse_qs(urlsplit(build_url(ReferenceQuery(title="K-sparse autoencoders"), 10)).query)
    assert '"' not in params["filter"][0]


def test_build_url_carries_the_contact_address_when_one_is_configured():
    with patch.dict("os.environ", {"CLAIMTRACE_CONTACT_MAILTO": "someone@example.org"}):
        params = parse_qs(urlsplit(build_url(ReferenceQuery(title="x"), 10)).query)
    assert params["mailto"] == ["someone@example.org"]


def test_build_url_never_carries_the_api_key():
    # The key goes in a header instead: the live benchmark logs every request
    # URL it fetched into a report meant to be committed.
    with patch.dict("os.environ", {"OPENALEX_API_KEY": "opaque-key"}):
        url = build_url(ReferenceQuery(title="x"), 10)
    assert "opaque-key" not in url
    assert "api_key" not in url


def test_identifier_filter_asks_by_the_reference_doi():
    assert identifier_filter(ReferenceQuery(doi="https://doi.org/10.18653/v1/P17-1171")) == (
        "doi:10.18653/v1/p17-1171"
    )


def test_identifier_filter_uses_the_doi_arxiv_registers_for_a_preprint():
    # Measured: ``filter=doi:10.48550/arxiv.1502.03167`` returns the one record
    # for that preprint, so an arXiv identifier is spendable here as a DOI.
    assert identifier_filter(ReferenceQuery(arxiv_id="1502.03167")) == (
        "doi:10.48550/arxiv.1502.03167"
    )


def test_identifier_filter_is_empty_without_an_identifier():
    assert identifier_filter(ReferenceQuery(title="x")) == ""


def test_identifier_filter_refuses_a_doi_the_filter_grammar_would_misread():
    # ``|`` is OpenAlex's OR and ``,`` splits the filter list; either would make
    # the request mean something other than "this DOI". Measured: the request
    # still answers 200 for ``|``, so the misreading would be silent.
    assert identifier_filter(ReferenceQuery(doi="10.1234/a|b")) == ""
    assert identifier_filter(ReferenceQuery(doi="10.1234/a,b")) == ""


def test_build_identifier_url_asks_by_doi():
    params = parse_qs(urlsplit(build_identifier_url(
        ReferenceQuery(title="Reading Wikipedia to Answer Open-Domain Questions",
                       doi="10.18653/v1/P17-1171"), 10
    )).query)
    assert params["filter"] == ["doi:10.18653/v1/p17-1171"]
    assert params["per-page"] == ["10"]


# --- Transport ----------------------------------------------------------------


def test_search_maps_a_body_onto_candidates():
    response, call = _search({"results": [_ACL_ITEM, _PREPRINT_ITEM]})
    assert response.status == "ok"
    assert [candidate.record_id for candidate in response.candidates] == [
        "W2963472678",
        "W2963472679",
    ]
    assert call.call_args.args[0].startswith("https://api.openalex.org/works?")


def test_search_passes_the_limit_and_timeout_through():
    _, call = _search({"results": []}, limit=4, timeout_seconds=3.5)
    assert "per-page=4" in call.call_args.args[0]
    assert call.call_args.kwargs["timeout_seconds"] == 3.5


def test_search_sends_a_configured_key_as_a_bearer_header():
    with patch.dict("os.environ", {"OPENALEX_API_KEY": "opaque-key"}):
        _, call = _search({"results": []})
    assert call.call_args.kwargs["headers"] == {"Authorization": "Bearer opaque-key"}


def test_search_sends_no_authorization_without_a_key():
    # Anonymous is a working configuration: the request is answered out of the
    # budget OpenAlex shares per address, and it must not carry an empty header.
    with patch.dict("os.environ", {}, clear=True):
        _, call = _search({"results": []})
    assert call.call_args.kwargs["headers"] == {}


def test_a_key_left_blank_is_no_key():
    with patch.dict("os.environ", {"OPENALEX_API_KEY": "   "}):
        _, call = _search({"results": []})
    assert call.call_args.kwargs["headers"] == {}


def test_search_without_a_title_or_identifier_does_not_make_a_request():
    with patch("engine.openalex_lookup.http_get_json") as call:
        response = OpenAlexLookup().search(ReferenceQuery(authors=["Artem Babenko"]))
    assert response.status == "ok"
    assert response.candidates == []
    assert call.called is False


def test_search_asks_a_doi_only_reference_by_doi():
    # No title to fall back to, so the identifier request is the only one -- but
    # it is made, where a title-only rule would have returned nothing at all.
    response, call = _search({"results": [_ACL_ITEM]}, ReferenceQuery(
        doi="10.18653/v1/P17-1171"
    ))
    assert [candidate.record_id for candidate in response.candidates] == ["W2963472678"]
    assert "filter=doi" in call.call_args.args[0].replace("%3A", ":").replace("%2F", "/")
    assert call.call_count == 1


def test_search_stops_at_the_identifier_when_it_identifies_the_work():
    response, call = _search({"results": [_ACL_ITEM]}, ReferenceQuery(
        title="Reading Wikipedia to Answer Open-Domain Questions",
        doi="10.18653/v1/P17-1171",
    ))
    assert [candidate.record_id for candidate in response.candidates] == ["W2963472678"]
    assert call.call_count == 1


def test_search_falls_back_to_the_title_when_the_identifier_finds_nothing():
    # A DOI the index does not hold is not evidence that the work is absent.
    # Measured: a reference can cite a DOI OpenAlex has not linked to its record.
    with patch(
        "engine.openalex_lookup.http_get_json",
        side_effect=[_http({"results": []}), _http({"results": [_ACL_ITEM]})],
    ) as call:
        response = OpenAlexLookup().search(ReferenceQuery(
            title="Reading Wikipedia to Answer Open-Domain Questions",
            doi="10.9999/not-indexed",
        ))
    assert [candidate.record_id for candidate in response.candidates] == ["W2963472678"]
    assert call.call_count == 2
    assert "filter=doi" in call.call_args_list[0].args[0].replace("%3A", ":").replace("%2F", "/")
    assert "title.search" in call.call_args_list[1].args[0]


def test_search_does_not_fall_back_when_the_identifier_request_fails():
    # A failed request is no evidence either way, and a second request into a
    # throttle spends the budget twice. The failure is returned as it is.
    with patch(
        "engine.openalex_lookup.http_get_json",
        return_value=_http(status_code=429, error="HTTP 429 Too Many Requests"),
    ) as call:
        response = OpenAlexLookup().search(ReferenceQuery(title="x", doi="10.9999/not-indexed"))
    assert response.status == "rate_limited"
    assert call.call_count == 1


def test_search_does_not_fall_back_without_a_title():
    with patch(
        "engine.openalex_lookup.http_get_json",
        return_value=_http({"results": []}),
    ) as call:
        response = OpenAlexLookup().search(ReferenceQuery(doi="10.9999/not-indexed"))
    assert response.status == "ok"
    assert response.candidates == []
    assert call.call_count == 1


def test_search_maps_a_throttle():
    with patch(
        "engine.openalex_lookup.http_get_json",
        return_value=_http(status_code=429, error="HTTP 429 Too Many Requests"),
    ):
        response = OpenAlexLookup().search(ReferenceQuery(title="x"))
    assert response.status == "rate_limited"
    assert response.error_code == "OPENALEX_RATE_LIMITED"


def test_search_treats_a_404_as_an_empty_answer_not_a_failure():
    with patch(
        "engine.openalex_lookup.http_get_json",
        return_value=_http(status_code=404, error="HTTP 404 Not Found"),
    ):
        response = OpenAlexLookup().search(ReferenceQuery(title="x"))
    assert response.status == "ok"
    assert response.candidates == []


def test_search_maps_a_server_error():
    with patch(
        "engine.openalex_lookup.http_get_json",
        return_value=_http(status_code=503, error="HTTP 503 Service Unavailable"),
    ):
        response = OpenAlexLookup().search(ReferenceQuery(title="x"))
    assert response.status == "failed"
    assert response.error_code == "OPENALEX_HTTP_503"


def test_search_maps_a_transport_failure():
    with patch(
        "engine.openalex_lookup.http_get_json",
        return_value=_http(status_code=0, error="request failed: timed out"),
    ):
        response = OpenAlexLookup().search(ReferenceQuery(title="x"))
    assert response.status == "failed"
    assert response.error_code == "OPENALEX_TRANSPORT"


# --- Against the identity rule ------------------------------------------------


def test_the_acl_record_is_identified_with_its_venue_from_raw_source_name():
    query = ReferenceQuery(
        title="Reading Wikipedia to Answer Open-Domain Questions",
        authors=["Danqi Chen"],
        year=2017,
        venue=_ACL_2017,
    )
    response, _ = _search({"results": [_ACL_ITEM]}, query=query)
    decision = select_identity(query, response.candidates)
    assert decision.status == "found"
    assert decision.selected is not None
    assert decision.selected.record_id == "W2963472678"


def test_the_hijacked_record_is_rejected_end_to_end():
    query = ReferenceQuery(
        title="Attention is all you need",
        authors=["Ashish Vaswani"],
        year=2017,
        venue="Advances in Neural Information Processing Systems",
    )
    response, _ = _search({"results": [_HIJACKED_ITEM]}, query=query)
    decision = select_identity(query, response.candidates)
    assert decision.status == "not_found"
    assert [item.reason for item in decision.rejected] == ["no venue"]


def test_asking_by_identifier_does_not_let_the_hijacked_record_through():
    # Measured 2026-10-15: `filter=doi:10.48550/arxiv.1706.03762` returns one
    # record, and it is this hijacked preprint -- the identifier query asks
    # exactly and OpenAlex answers with a record that carries the identifier as
    # its location. The reference's own DOI is not that record's DOI, so the
    # pre-pass has nothing to match, and the rules refuse it exactly as they do
    # when the title search returns it. That is the point: the identifier
    # changes what is asked, never what is accepted.
    query = ReferenceQuery(
        title="Attention is all you need",
        authors=["Ashish Vaswani"],
        year=2017,
        venue="Advances in Neural Information Processing Systems",
        doi="10.48550/arxiv.1706.03762",
    )
    response, call = _search({"results": [_HIJACKED_ITEM]}, query=query)
    assert "filter=doi" in call.call_args.args[0].replace("%3A", ":")
    assert call.call_count == 1
    decision = select_identity(query, response.candidates)
    assert decision.status == "not_found"
    assert decision.rule != "doi"
