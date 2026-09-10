"""Adapt Engine Scholar candidates to traceable bibliography audit records."""

import hashlib
import re
from datetime import UTC, datetime
from urllib.parse import urlsplit

from ..audit_models import (
    BibliographicMetadata,
    ExternalRecord,
    LookupAttempt,
    LookupResult,
    ReferenceEntry,
)


def _normalize(value: str) -> str:
    return " ".join(value.casefold().split())


def _search_authors(authors: list[str]) -> list[str]:
    """Adapt standard IEEE initials to the Engine's surname-first query format."""
    if not authors or "," in authors[0]:
        return authors
    match = re.fullmatch(r"((?:[A-Z]\.\s*)+)(.+)", authors[0])
    if match:
        return [f"{match.group(2).strip()}, {match.group(1).strip()}", *authors[1:]]
    return authors


class GoogleScholarLookup:
    def lookup(self, entry: ReferenceEntry) -> LookupResult:
        # Lazy import allows API startup without loading the network client.
        from engine.scholar_search import search_scholar

        outcome = search_scholar(
            title=entry.metadata.title,
            authors=_search_authors(entry.metadata.authors),
            year=entry.metadata.year,
        )
        records = []
        invalid_url = False
        for hit in outcome.results:
            parsed = urlsplit(hit.url)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                invalid_url = True
                continue
            records.append(
                ExternalRecord(
                    provider="google_scholar",
                    record_id="scholar:" + hashlib.sha256(hit.url.encode()).hexdigest(),
                    url=hit.url,
                    retrieved_at=datetime.now(UTC),
                    metadata=BibliographicMetadata(
                        title=hit.title,
                        authors=hit.authors,
                        year=hit.year,
                        venue="" if hit.venue in {"NA", "N/A"} else hit.venue,
                    ),
                )
            )
        status = outcome.status
        if status == "rate_limited":
            detail = outcome.error or "Google Scholar rate-limited the search."
            return LookupResult(
                outcome="failed",
                records=[],
                attempts=[
                    LookupAttempt(
                        provider="google_scholar",
                        outcome="failed",
                        error_code="SCHOLAR_RATE_LIMITED",
                        detail=detail,
                    )
                ],
                reason=(
                    f"{detail} Retry later or reduce the number of lookups per audit; "
                    "publication existence remains unchecked."
                ),
            )
        reason = (
            outcome.error
            or {
                "found": "Google Scholar returned a publication candidate.",
                "ambiguous": "Multiple publication candidates require review.",
                "not_found": "No publication candidate was returned for this query.",
                "failed": "Google Scholar lookup failed.",
            }[status]
        )
        if invalid_url:
            status = "ambiguous" if records else "failed"
            reason = "Some search hits lack a usable publication URL; identity remains unchecked."
        # A single search hit is not, by itself, proof of publication identity.
        if status == "found" and records:
            if _normalize(records[0].metadata.title) != _normalize(entry.metadata.title):
                status = "ambiguous"
                reason = "The returned title differs from the reference; review this candidate."
        return LookupResult(
            outcome=status,
            records=records,
            attempts=[
                LookupAttempt(
                    provider="google_scholar",
                    outcome=status,
                    error_code="SCHOLAR_SEARCH_FAILED" if status == "failed" else None,
                    detail=reason,
                )
            ],
            reason=reason,
        )
