"""Tests for metadata_lookup.py.

The providers here are hand-written fakes, so the chain's behaviour is pinned
without any network access or recorded fixture.
"""

import json
import urllib.error
from unittest.mock import patch

from engine.identity import PublicationCandidate, ReferenceQuery
from engine.metadata_lookup import (
    ProviderResponse,
    default_user_agent,
    http_get_json,
    lookup_reference,
)

_TPAMI = "IEEE Transactions on Pattern Analysis and Machine Intelligence"
_QUERY = ReferenceQuery(
    title="The inverted multi-index",
    authors=["Artem Babenko", "Victor Lempitsky"],
    year=2014,
    venue=_TPAMI,
)


def _record(record_id: str = "W11", year: int | None = 2014, **overrides) -> PublicationCandidate:
    fields = {
        "provider": "openalex",
        "record_id": record_id,
        "title": "The inverted multi-index",
        "authors": ["Artem Babenko", "Victor Lempitsky"],
        "year": year,
        "venue": _TPAMI,
        "kind": "journal-article",
    }
    fields.update(overrides)
    return PublicationCandidate(**fields)


class _FakeProvider:
    """A provider that returns a canned response, or raises."""

    def __init__(self, name, response=None, raises=None):
        self.name = name
        self._response = response
        self._raises = raises
        self.calls: list[dict] = []

    def search(self, query, *, limit, timeout_seconds):
        self.calls.append({"query": query, "limit": limit, "timeout_seconds": timeout_seconds})
        if self._raises is not None:
            raise self._raises
        return self._response


def _ok(*candidates) -> ProviderResponse:
    return ProviderResponse(status="ok", candidates=list(candidates))


def _failed() -> ProviderResponse:
    return ProviderResponse(status="failed", error_code="CROSSREF_HTTP_500", error="HTTP 500")


def _throttled() -> ProviderResponse:
    return ProviderResponse(
        status="rate_limited", error_code="OPENALEX_RATE_LIMITED", error="HTTP 429"
    )


# --- Chain semantics ----------------------------------------------------------


def test_the_chain_stops_at_the_first_provider_that_settles_it():
    first = _FakeProvider("openalex", _ok(_record()))
    second = _FakeProvider("crossref", _ok(_record(record_id="W99")))
    result = lookup_reference(_QUERY, [first, second])
    assert result.outcome == "found"
    assert result.rule == "exact-title"
    assert result.selected is not None
    assert result.selected.record_id == "W11"
    assert second.calls == []
    assert len(result.attempts) == 1


def test_a_later_provider_can_supply_the_decisive_record():
    first = _FakeProvider("openalex", _ok(_record(record_id="W1", year=2010)))
    second = _FakeProvider("crossref", _ok(_record(record_id="W2", year=2014)))
    result = lookup_reference(_QUERY, [first, second])
    assert result.outcome == "found"
    assert result.selected is not None
    assert result.selected.record_id == "W2"
    assert [attempt.outcome for attempt in result.attempts] == ["not_found", "found"]
    # The attempt outcome describes the chain up to that provider, so the first
    # one reads not_found even though the reference was ultimately resolved.
    assert result.attempts[0].candidate_count == 1
    assert result.attempts[1].candidate_count == 1


def test_a_completed_provider_plus_a_failed_one_is_failed_not_not_found():
    # The single most important rule in this module. One provider answered and
    # found nothing; the other never answered. Reporting not_found would turn a
    # partial search into a conclusion about the world.
    first = _FakeProvider("openalex", _ok())
    second = _FakeProvider("crossref", _failed())
    result = lookup_reference(_QUERY, [first, second])
    assert result.outcome == "failed"
    assert [attempt.outcome for attempt in result.attempts] == ["not_found", "failed"]
    assert result.attempts[1].error_code == "CROSSREF_HTTP_500"
    assert "did not complete" in result.reason


def test_every_provider_completing_without_identity_is_not_found():
    first = _FakeProvider("openalex", _ok())
    second = _FakeProvider("crossref", _ok())
    result = lookup_reference(_QUERY, [first, second])
    assert result.outcome == "not_found"
    assert [attempt.outcome for attempt in result.attempts] == ["not_found", "not_found"]


def test_every_provider_throttled_is_rate_limited():
    first = _FakeProvider("openalex", _throttled())
    second = _FakeProvider("crossref", _throttled())
    result = lookup_reference(_QUERY, [first, second])
    assert result.outcome == "rate_limited"
    assert result.attempts[0].error_code == "OPENALEX_RATE_LIMITED"


def test_a_failure_outranks_a_throttle():
    first = _FakeProvider("openalex", _throttled())
    second = _FakeProvider("crossref", _failed())
    result = lookup_reference(_QUERY, [first, second])
    assert result.outcome == "failed"


def test_a_provider_that_raises_does_not_take_the_chain_down():
    first = _FakeProvider("openalex", raises=RuntimeError("connection reset"))
    second = _FakeProvider("crossref", _ok(_record(record_id="W2")))
    result = lookup_reference(_QUERY, [first, second])
    assert result.outcome == "found"
    assert result.selected is not None
    assert result.selected.record_id == "W2"
    assert result.attempts[0].error_code == "PROVIDER_RAISED"
    assert "RuntimeError" in result.attempts[0].error


def test_an_ambiguous_result_survives_an_incomplete_provider():
    # Ambiguous does not claim the search was exhaustive, so it is still worth
    # returning -- but the reason has to say the candidate set is partial.
    first = _FakeProvider("openalex", _ok(_record(record_id="W1", year=2011),
                                          _record(record_id="W2", year=2012)))
    second = _FakeProvider("crossref", _throttled())
    result = lookup_reference(
        ReferenceQuery(title="The inverted multi-index", year=2012, venue=""), [first, second]
    )
    assert result.outcome == "ambiguous"
    assert len(result.candidates) == 2
    assert "did not complete" not in result.reason
    assert "rate-limited" in result.reason
    assert "some sources were not searched" in result.reason


def test_no_providers_is_a_configuration_error():
    result = lookup_reference(_QUERY, [])
    assert result.outcome == "failed"
    assert result.attempts == []
    assert "No metadata providers are configured" in result.reason


def test_rejections_reach_the_result():
    spoof = _record(record_id="W1", year=2025, venue="", kind="posted-content")
    result = lookup_reference(_QUERY, [_FakeProvider("crossref", _ok(spoof))])
    assert result.outcome == "not_found"
    assert [item.record_id for item in result.rejected] == ["W1"]


def test_the_configured_limit_and_timeout_reach_the_provider():
    provider = _FakeProvider("openalex", _ok())
    lookup_reference(_QUERY, [provider], limit=3, timeout_seconds=2.5)
    assert provider.calls[0]["limit"] == 3
    assert provider.calls[0]["timeout_seconds"] == 2.5
    assert provider.calls[0]["query"] is _QUERY


def test_a_provider_without_a_name_still_yields_an_attempt():
    class _Anonymous:
        def search(self, query, *, limit, timeout_seconds):
            return _failed()

    result = lookup_reference(_QUERY, [_Anonymous()])
    assert result.attempts[0].provider == "_Anonymous"


# --- The HTTP seam ------------------------------------------------------------


class _FakeResponse:
    def __init__(self, payload: bytes, status: int = 200):
        self._payload = payload
        self.status = status

    def read(self, amount: int | None = None) -> bytes:
        return self._payload if amount is None else self._payload[:amount]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_http_get_json_parses_a_json_body():
    with patch("engine.metadata_lookup.urllib.request.urlopen") as urlopen:
        urlopen.return_value = _FakeResponse(json.dumps({"ok": True}).encode())
        result = http_get_json("https://api.example.org/works")
    assert result.status_code == 200
    assert result.body == {"ok": True}
    assert result.error == ""


def test_http_get_json_reports_an_error_status_without_raising():
    error = urllib.error.HTTPError("https://api.example.org", 429, "Too Many Requests", {}, None)
    with patch("engine.metadata_lookup.urllib.request.urlopen", side_effect=error):
        result = http_get_json("https://api.example.org/works")
    assert result.status_code == 429
    assert result.body is None
    assert "429" in result.error


def test_http_get_json_reports_a_transport_failure():
    failure = urllib.error.URLError("nodename nor servname provided")
    with patch("engine.metadata_lookup.urllib.request.urlopen", side_effect=failure):
        result = http_get_json("https://api.example.org/works")
    assert result.status_code == 0
    assert "request failed" in result.error


def test_http_get_json_reports_a_body_that_is_not_json():
    with patch("engine.metadata_lookup.urllib.request.urlopen") as urlopen:
        urlopen.return_value = _FakeResponse(b"<html>gateway timeout</html>")
        result = http_get_json("https://api.example.org/works")
    assert result.status_code == 200
    assert result.body is None
    assert "not JSON" in result.error


def test_http_get_json_stops_an_oversized_body():
    with patch("engine.metadata_lookup.MAX_RESPONSE_BYTES", 16):
        with patch("engine.metadata_lookup.urllib.request.urlopen") as urlopen:
            urlopen.return_value = _FakeResponse(b"x" * 17)
            result = http_get_json("https://api.example.org/works")
    assert result.body is None
    assert "size cap" in result.error


def test_http_get_json_sends_the_user_agent_and_accept_header():
    with patch("engine.metadata_lookup.urllib.request.urlopen") as urlopen:
        urlopen.return_value = _FakeResponse(b"{}")
        http_get_json("https://api.example.org/works", user_agent="TestAgent/1")
    sent = urlopen.call_args.args[0]
    assert sent.get_header("User-agent") == "TestAgent/1"
    assert sent.get_header("Accept") == "application/json"


def test_the_user_agent_carries_a_contact_address_only_when_one_is_configured():
    with patch.dict("os.environ", {}, clear=True):
        assert "mailto:" not in default_user_agent()
    with patch.dict("os.environ", {"CLAIMTRACE_CONTACT_MAILTO": "someone@example.org"}):
        assert default_user_agent().endswith("mailto:someone@example.org")
