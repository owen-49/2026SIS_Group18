"""Check the backend adapter against Engine results without external queries."""

from unittest.mock import patch

from backend.src.audit_models import ReferenceEntry
from backend.src.models import BibEntryRecord
from backend.src.services.google_scholar_lookup import GoogleScholarLookup

from engine.scholar_search import ScholarResult, ScholarSearchOutcome


def lookup(status, hits):
    entry = ReferenceEntry(entry_id="ref-1", metadata=BibEntryRecord(key="ref-1", title="My title"))
    with patch(
        "engine.scholar_search.search_scholar",
        return_value=ScholarSearchOutcome(
            status=status,
            results=hits,
        ),
    ):
        return GoogleScholarLookup().lookup(entry)


def test_record_keeps_real_publication_url():
    result = lookup("found", [ScholarResult(title="My title", url="https://example.org/paper")])
    assert result.outcome == "found"
    assert str(result.records[0].url) == "https://example.org/paper"
    assert result.records[0].retrieved_at is not None


def test_unrelated_single_hit_is_a_candidate():
    result = lookup("found", [ScholarResult(title="Different title", url="https://example.org/p")])
    assert result.outcome == "ambiguous"


def test_missing_url_is_not_replaced_with_homepage():
    result = lookup("found", [ScholarResult(title="My title")])
    assert result.outcome == "failed"
    assert not result.records


def test_network_failure_is_not_not_found():
    assert lookup("failed", []).outcome == "failed"
    assert lookup("not_found", []).outcome == "not_found"


def test_rate_limited_is_failed_with_distinct_code():
    result = lookup("rate_limited", [])
    assert result.outcome == "failed"
    assert result.attempts[0].error_code == "SCHOLAR_RATE_LIMITED"
    assert not result.records
    assert "Retry later" in result.reason
