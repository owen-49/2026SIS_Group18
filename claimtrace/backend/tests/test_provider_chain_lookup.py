"""The provider-chain adapter, pinned against hand-written providers.

Every provider here is a fake, so the whole suite runs offline and the
assertions are about the translation into the audit wire model rather than
about what OpenAlex happens to return today. The cases that were ported from
the deleted Scholar adapter's tests keep their names close to the originals,
because they were asserting this contract before this module existed.
"""

from datetime import UTC, datetime

import pytest
from backend.src.audit_models import LookupResult, ReferenceEntry
from backend.src.models import BibEntryRecord
from backend.src.services import provider_chain_lookup as chain
from backend.src.services.provider_chain_lookup import ProviderChainLookup
from engine.identity import PublicationCandidate
from engine.metadata_lookup import (
    MetadataLookupResult,
    ProviderAttempt,
    ProviderResponse,
)

# A reference-list entry as a PDF produces it: the structured fields are empty
# and everything worth having is in the raw text.
RAW = (
    "[3] Devamanyu Hazarika, Soujanya Poria, Rada Mihalcea, Erik Cambria, and "
    "Roger Zimmermann. 2018. Icon: Interactive conversational memory network for "
    "multimodal emotion detection. In Proceedings of the 2018 conference on empirical "
    "methods in natural language processing. 2594-2604."
)

TITLE = "ICON: Interactive Conversational Memory Network for Multimodal Emotion Detection"

# What the reference-text parser makes of RAW: the real corpus title, cased as
# the reference list gives it rather than as the published record does.
PARSED_TITLE = "Icon: Interactive conversational memory network for multimodal emotion detection"


def entry(**overrides) -> ReferenceEntry:
    fields = {"key": "hazarika2018icon", "raw_text": RAW}
    fields.update(overrides)
    return ReferenceEntry(entry_id="entry-1", metadata=BibEntryRecord(**fields))


def candidate(**overrides) -> PublicationCandidate:
    fields = {
        "provider": "openalex",
        "record_id": "W2963504627",
        "title": TITLE,
        "authors": ["Devamanyu Hazarika"],
        "year": 2018,
        "venue": "Proceedings of the 2018 Conference on Empirical Methods in NLP",
        "kind": "conference-paper",
        "doi": "10.18653/v1/d18-1280",
        "url": "https://doi.org/10.18653/v1/d18-1280",
    }
    fields.update(overrides)
    return PublicationCandidate(**fields)


class FakeProvider:
    """A provider that returns a canned response and records the query."""

    def __init__(self, name, response):
        self.name = name
        self._response = response
        self.queries = []

    def search(self, query, *, limit, timeout_seconds):
        self.queries.append(query)
        return self._response


def ok(*candidates) -> ProviderResponse:
    return ProviderResponse(status="ok", candidates=list(candidates))


def throttled(name="openalex") -> ProviderResponse:
    return ProviderResponse(
        status="rate_limited", error_code=f"{name.upper()}_RATE_LIMITED", error="HTTP 429"
    )


def failed(name="crossref") -> ProviderResponse:
    return ProviderResponse(
        status="failed", error_code=f"{name.upper()}_HTTP_500", error="HTTP 500"
    )


def lookup(*providers, **kwargs) -> LookupResult:
    return ProviderChainLookup(list(providers), **kwargs).lookup(entry())


# --- The query this adapter hands the chain -----------------------------------


def test_a_reference_with_only_raw_text_is_queried_from_it():
    # The guard in the audit service used to read the structured title, which a
    # PDF reference never has. This is the case that makes the whole path live.
    provider = FakeProvider("openalex", ok(candidate()))
    lookup(provider)
    query = provider.queries[0]
    assert query.title == PARSED_TITLE
    assert query.authors[0] == "Devamanyu Hazarika"
    assert query.year == 2018
    assert query.venue.startswith("Proceedings of the 2018 conference")


def test_structured_fields_win_over_the_raw_text():
    provider = FakeProvider("openalex", ok(candidate()))
    ProviderChainLookup([provider]).lookup(
        entry(title="A Different Title", authors=["Someone Else"], year=2001)
    )
    query = provider.queries[0]
    assert query.title == "A Different Title"
    assert query.authors == ["Someone Else"]
    assert query.year == 2001


def test_a_bibtex_block_is_never_parsed_as_a_reference_entry():
    # Parsing one recovers a corrupted DOI ("10.1234/example}") that would
    # silently disable the identifier tier in select_identity, plus author
    # names made of the block's own punctuation. The block below carries no
    # structured fields, so skipping the parse leaves nothing to search with --
    # and nothing is the honest answer, since a real BibTeX entry always has
    # its fields populated by the parser that read it.
    provider = FakeProvider("openalex", ok(candidate()))
    result = ProviderChainLookup([provider]).lookup(
        entry(raw_text="@article{sample,\n title={Retrieval}, doi={10.1234/example}\n}")
    )
    assert provider.queries == []
    assert result.outcome == "failed"
    assert result.attempts[0].error_code == chain.NO_TITLE_CODE


def test_a_bibtex_entry_is_searched_with_its_structured_doi_not_a_parsed_one():
    # The case the guard exists for: the DOI the parser stored is the clean
    # "10.1234/example", and it must reach the provider unmodified. Reading the
    # block instead would substitute the corrupted form and, because a
    # normalised DOI can never equal the reference's, silently disable the one
    # identity tier that settles a match outright.
    provider = FakeProvider("openalex", ok(candidate()))
    ProviderChainLookup([provider]).lookup(
        entry(
            title="Retrieval with citations",
            authors=["J. Smith"],
            doi="10.1234/example",
            raw_text="@article{sample,\n title={Retrieval with citations},\n"
            " author={Smith, J.},\n doi={10.1234/example}\n}",
        )
    )
    query = provider.queries[0]
    assert query.doi == "10.1234/example"
    assert query.authors == ["J. Smith"]
    assert "}" not in query.doi


def test_a_reference_with_no_title_anywhere_is_not_searched():
    provider = FakeProvider("openalex", ok(candidate()))
    result = ProviderChainLookup([provider]).lookup(entry(raw_text=""))
    assert result.outcome == "failed"
    assert provider.queries == []
    assert result.attempts[0].error_code == chain.NO_TITLE_CODE


# --- Outcome mapping ----------------------------------------------------------


def test_the_chain_stops_at_the_first_provider_that_settles_the_reference():
    first = FakeProvider("openalex", ok(candidate()))
    second = FakeProvider("crossref", ok(candidate(provider="crossref")))
    result = lookup(first, second)
    assert result.outcome == "found"
    assert second.queries == []
    assert len(result.records) == 1


def test_a_found_record_carries_a_real_url_and_a_retrieval_time():
    before = datetime.now(UTC)
    result = lookup(FakeProvider("openalex", ok(candidate())))
    record = result.records[0]
    assert str(record.url) == "https://doi.org/10.18653/v1/d18-1280"
    assert record.retrieved_at >= before
    assert record.metadata.title == TITLE


def test_an_unrelated_single_hit_is_a_candidate_not_a_match():
    result = lookup(FakeProvider("openalex", ok(candidate(title="A Completely Different Work"))))
    assert result.outcome in {"failed", "not_found"}
    assert result.records == []


def test_a_network_failure_is_not_not_found():
    # The single most important rule: one provider answered and found nothing,
    # the other never answered. Reporting not_found would turn a partial search
    # into a conclusion about the world.
    result = lookup(FakeProvider("openalex", ok()), FakeProvider("crossref", failed()))
    assert result.outcome == "failed"
    # An attempt describes the chain up to and including its provider, so the
    # first one reads not_found -- which is why the outcome cannot be read off
    # any single attempt. The last is the adapter's own verdict, appended after
    # the provider attempts rather than replacing them.
    assert [attempt.outcome for attempt in result.attempts] == [
        "not_found",
        "failed",
        "failed",
    ]
    assert result.attempts[1].error_code == "CROSSREF_HTTP_500"
    assert result.attempts[-1].provider == chain.CHAIN_PROVIDER


def test_a_throttled_provider_beside_a_completed_one_is_not_not_found():
    # The same rule for a provider that was rate-limited. A naive mapping would
    # emit not_found carrying a failed attempt, which LookupResult rejects; the
    # service's broad except would then flatten it into LOOKUP_FAILED and lose
    # the cause entirely.
    result = lookup(FakeProvider("openalex", ok()), FakeProvider("crossref", throttled("crossref")))
    assert result.outcome == "failed"
    # The throttle survives as a failure carrying its own code, so the report
    # says which source needs retrying rather than only that something did.
    assert result.attempts[1].error_code == "CROSSREF_RATE_LIMITED"
    assert result.records == []
    LookupResult.model_validate(result.model_dump())


def test_a_throttled_chain_downgrades_a_not_found_from_the_engine(monkeypatch):
    # The second line. The engine no longer produces this, but the adapter must
    # not depend on that: an engine that did would otherwise hand the wire model
    # a not_found carrying a rate-limited attempt.
    hand_built = MetadataLookupResult(
        outcome="not_found",
        query=chain.reference_query_for(entry()),
        reason="the providers returned no records for this reference",
        attempts=[
            ProviderAttempt(provider="openalex", outcome="rate_limited", error_code="OA_RATE"),
            ProviderAttempt(provider="crossref", outcome="not_found"),
        ],
    )
    monkeypatch.setattr(chain, "lookup_reference", lambda *a, **k: hand_built)
    result = ProviderChainLookup([FakeProvider("openalex", ok())]).lookup(entry())
    assert result.outcome == "failed"
    # The downgrade names the provider that did not complete, not a generic
    # code: the point of refusing to call this not_found is that the reader can
    # go and retry the source that was throttled.
    assert result.attempts[-1].error_code == "OA_RATE"
    assert result.attempts[-1].provider == chain.CHAIN_PROVIDER
    LookupResult.model_validate(result.model_dump())


def test_the_incomplete_downgrade_falls_back_when_no_attempt_names_a_cause(monkeypatch):
    # The code above is only as good as the attempt carrying it. An attempt that
    # failed without one leaves the downgrade with nothing to report, and the
    # generic code is what stops the wire model from receiving a failure with an
    # empty explanation.
    hand_built = MetadataLookupResult(
        outcome="not_found",
        query=chain.reference_query_for(entry()),
        attempts=[
            ProviderAttempt(provider="openalex", outcome="failed"),
            ProviderAttempt(provider="crossref", outcome="not_found"),
        ],
    )
    monkeypatch.setattr(chain, "lookup_reference", lambda *a, **k: hand_built)
    result = ProviderChainLookup([FakeProvider("openalex", ok())]).lookup(entry())
    assert result.outcome == "failed"
    assert result.attempts[-1].error_code == chain.INCOMPLETE_CODE


def test_rate_limited_is_failed_with_a_distinct_code():
    result = lookup(FakeProvider("openalex", throttled()), FakeProvider("crossref", throttled()))
    assert result.outcome == "failed"
    assert result.records == []
    assert result.attempts[0].error_code == "OPENALEX_RATE_LIMITED"
    assert "retry later" in result.attempts[0].detail
    assert "retry later" in result.reason or "rate-limited" in result.reason


def test_every_provider_completing_without_identity_is_not_found():
    result = lookup(FakeProvider("openalex", ok()), FakeProvider("crossref", ok()))
    assert result.outcome == "not_found"
    assert all(attempt.outcome == "not_found" for attempt in result.attempts)


def test_a_chain_with_no_providers_reports_a_configuration_failure():
    result = lookup()
    assert result.outcome == "failed"
    assert result.attempts[0].error_code == chain.NO_PROVIDERS_CODE
    LookupResult.model_validate(result.model_dump())


# --- URLs ---------------------------------------------------------------------


def test_a_record_without_a_url_falls_back_to_its_doi_resolver():
    result = lookup(FakeProvider("openalex", ok(candidate(url=""))))
    assert result.outcome == "found"
    assert str(result.records[0].url) == "https://doi.org/10.18653/v1/d18-1280"


def test_a_record_with_neither_url_nor_doi_is_not_given_a_homepage():
    # Ported from the Scholar adapter: a fabricated location is worse than no
    # record, and the wire model requires an absolute http(s) URL anyway.
    result = lookup(FakeProvider("openalex", ok(candidate(url="", doi=""))))
    assert result.outcome == "failed"
    assert result.records == []
    assert result.attempts[-1].error_code == chain.NO_URL_CODE


@pytest.mark.parametrize("bad", ["ftp://example.org/x", "example.org/x", "javascript:alert(1)"])
def test_a_non_http_url_is_not_emitted_as_a_record(bad):
    result = lookup(FakeProvider("openalex", ok(candidate(url=bad, doi=""))))
    assert result.outcome == "failed"
    assert result.records == []


def test_the_adapter_failure_is_reported_beside_what_the_providers_did():
    # Otherwise the report reads "failed" next to an attempt that succeeded,
    # with nothing to explain the difference.
    result = lookup(FakeProvider("openalex", ok(candidate(url="", doi=""))))
    assert [attempt.provider for attempt in result.attempts] == ["openalex", chain.CHAIN_PROVIDER]
    assert result.attempts[0].outcome == "found"


# --- Record identity ----------------------------------------------------------


def test_record_ids_name_their_provider_and_are_stable():
    first = lookup(FakeProvider("openalex", ok(candidate()))).records[0]
    second = lookup(FakeProvider("openalex", ok(candidate()))).records[0]
    assert first.record_id == "openalex:W2963504627"
    assert first.record_id == second.record_id


def test_the_provider_is_carried_through_to_the_record():
    record = lookup(FakeProvider("openalex", ok(candidate()))).records[0]
    assert record.provider == "openalex"


def test_the_reason_names_the_rule_that_decided_the_match():
    # The rule is not on the wire anywhere else, and engine.identity keeps it
    # precisely so a report can answer "which tier decided this?".
    result = lookup(FakeProvider("openalex", ok(candidate())))
    assert "exact-title" in result.reason


# --- Robustness ---------------------------------------------------------------


def test_a_provider_that_raises_does_not_escape_the_adapter():
    class Exploding:
        name = "exploding"

        def search(self, query, *, limit, timeout_seconds):
            raise RuntimeError("provider blew up")

    result = lookup(Exploding(), FakeProvider("crossref", ok(candidate(provider="crossref"))))
    assert result.outcome in {"found", "failed", "not_found"}


def test_an_unexpected_adapter_fault_becomes_a_failed_lookup(monkeypatch):
    def explode(*args, **kwargs):
        raise RuntimeError("unexpected")

    monkeypatch.setattr(chain, "reference_query_for", explode)
    result = ProviderChainLookup([FakeProvider("openalex", ok())]).lookup(entry())
    assert result.outcome == "failed"
    assert result.attempts[0].error_code == chain.ADAPTER_FAILED_CODE


@pytest.mark.parametrize(
    "providers",
    [
        [FakeProvider("openalex", ok(candidate()))],
        [FakeProvider("openalex", ok())],
        [FakeProvider("openalex", throttled())],
        [FakeProvider("openalex", failed())],
        [],
    ],
)
def test_every_outcome_satisfies_the_wire_model(providers):
    # The invariant this adapter exists to guarantee. LookupResult rejects a
    # not_found whose attempts are not all not_found, a found with more than one
    # record, and an ambiguous with none -- so revalidating each outcome is the
    # test that catches a mapping that would otherwise be swallowed by the audit
    # service's broad except and reported as LOOKUP_FAILED.
    result = ProviderChainLookup(list(providers)).lookup(entry())
    LookupResult.model_validate(result.model_dump())


def test_the_adapter_satisfies_the_bibliography_lookup_protocol():
    from backend.src.services.bibliography_lookup import BibliographyLookup

    adapter: BibliographyLookup = ProviderChainLookup([FakeProvider("openalex", ok())])
    assert adapter.lookup(entry()).outcome in {"found", "ambiguous", "not_found", "failed"}


def test_the_default_chain_is_openalex_then_crossref():
    names = [provider.name for provider in chain.default_providers()]
    assert names == ["openalex", "crossref"]
