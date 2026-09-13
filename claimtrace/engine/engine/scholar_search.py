"""Search Google Scholar for a bibliographic reference.

Provides the external "does this reference actually exist?" lookup used by the
bibliography Audit path. Unlike single-claim Verify (which judges semantic
support), this queries a public citation index and returns candidate records.

Design notes:
- ``scholarly`` is the free default provider. It is a best-effort scrape of
  Google Scholar and can be rate-limited or blocked; failures degrade to a
  ``failed`` outcome rather than raising, so a blocked search never takes the
  whole audit down.
- The module is storage-agnostic and returns its own value objects. The
  backend adapts these into its ``audit_models.LookupResult``.
"""

from dataclasses import dataclass, field
from itertools import islice
from typing import Any

from scholarly import DOSException, MaxTriesExceededException, scholarly

# scholarly retries a blocked request on its own (with 1-2s sleeps and, on 403,
# 60-120s sleeps). Bound that loop so a rate-limited Scholar fails fast instead
# of hanging a worker until the parent's hard timeout.
DEFAULT_REQUEST_TIMEOUT_SECONDS = 10
DEFAULT_MAX_TRIES = 2


@dataclass
class ScholarResult:
    """A single publication hit from Google Scholar."""

    title: str
    authors: list[str] = field(default_factory=list)
    year: int | None = None
    venue: str = ""
    url: str = ""


@dataclass
class ScholarSearchOutcome:
    """Result of searching Google Scholar for one reference."""

    status: str  # "found" | "ambiguous" | "not_found" | "failed" | "rate_limited"
    results: list[ScholarResult] = field(default_factory=list)
    error: str = ""


def _first_author_surname(authors: list[str] | None) -> str:
    """Extract a conservative first-author surname for query refinement."""
    if not authors:
        return ""
    first = authors[0].strip()
    if "," in first:  # "Last, First"
        return first.split(",")[0].strip()
    parts = first.split()
    return parts[0] if parts else ""


def _build_query(title: str, authors: list[str] | None) -> str:
    """Build a Scholar query: exact title plus first-author surname."""
    query = f'"{title}"'
    surname = _first_author_surname(authors)
    if surname:
        query += f" {surname}"
    return query


def _bib_to_result(pub: Any) -> ScholarResult | None:
    """Adapt a scholarly publication to a ScholarResult.

    scholarly 1.7.x returns plain dicts; older versions returned objects.
    Handle both so the search survives a library upgrade.
    """
    if isinstance(pub, dict):
        bib = pub.get("bib") or {}
        url = pub.get("pub_url") or pub.get("eprint_url") or ""
    else:
        bib = getattr(pub, "bib", None) or {}
        url = getattr(pub, "pub_url", "") or getattr(pub, "eprint_url", "") or ""

    if not isinstance(bib, dict):
        return None
    title = bib.get("title", "")
    if not title:
        return None

    authors = bib.get("author", []) or []
    year_raw = bib.get("pub_year", "")
    try:
        year = int(year_raw) if year_raw else None
    except (TypeError, ValueError):
        year = None
    venue = bib.get("venue", "") or bib.get("journal", "") or ""

    return ScholarResult(
        title=title,
        authors=list(authors),
        year=year,
        venue=venue,
        url=url,
    )


def search_scholar(
    title: str,
    authors: list[str] | None = None,
    year: int | None = None,
    *,
    max_results: int = 3,
    request_timeout_seconds: int = DEFAULT_REQUEST_TIMEOUT_SECONDS,
    max_tries: int = DEFAULT_MAX_TRIES,
) -> ScholarSearchOutcome:
    """Search Google Scholar for a reference by title / authors / year.

    Args:
        title: The reference title (required).
        authors: Optional author name strings (first author is used to refine).
        year: Optional publication year to bound the search.
        max_results: Maximum hits to collect before deciding the outcome.
        request_timeout_seconds: Per-request timeout passed to scholarly.
        max_tries: Bounds scholarly's internal retry loop before giving up.

    Returns:
        ``ScholarSearchOutcome`` with status ``found`` (one candidate),
        ``ambiguous`` (several), ``not_found`` (no hits), ``failed``
        (search error), or ``rate_limited`` (blocked / HTTP 429).
    """
    if not title or not title.strip():
        return ScholarSearchOutcome(status="failed", error="Reference title is required.")

    query = _build_query(title.strip(), authors)

    kwargs: dict[str, Any] = {}
    if year is not None:
        kwargs["year_low"] = year
        kwargs["year_high"] = year

    # Bound scholarly's own retry loop so a rate-limited (HTTP 429) or captcha
    # block fails fast instead of hanging the worker until the parent timeout.
    scholarly.set_timeout(request_timeout_seconds)
    scholarly.set_retries(max_tries)

    try:
        search = scholarly.search_pubs(query, **kwargs)
        hits = list(islice(search, max_results))
    except (MaxTriesExceededException, DOSException) as exc:
        return ScholarSearchOutcome(
            status="rate_limited",
            error=f"Google Scholar rate-limited the search: {exc}",
        )
    except Exception as exc:  # network / other — degrade, don't raise
        return ScholarSearchOutcome(
            status="failed",
            error=f"Google Scholar search failed: {exc}",
        )

    results = [r for r in (_bib_to_result(hit) for hit in hits) if r is not None]

    if not results:
        return ScholarSearchOutcome(status="not_found")
    if len(results) == 1:
        return ScholarSearchOutcome(status="found", results=results)
    return ScholarSearchOutcome(status="ambiguous", results=results)
