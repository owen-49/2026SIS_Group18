"""Query Crossref for a cited reference.

Crossref is the DOI registration agency's own index, so a record here is a
publisher's asserted metadata rather than a third party's guess. It is the
secondary provider in the chain: it covers published venues well and preprints
poorly, which is the opposite of OpenAlex.

Design notes:
- The query is built as title plus the first author's surname. Measured:
  without the surname the cited journal record for one reference sits at rank 9
  of Crossref's relevance ordering and with it at rank 2. The surname is a
  ranking hint, not evidence -- :func:`engine.identity.select_identity` decides
  identity and never treats a name as proof.
- The query is deliberately unquoted. Quotation marks are Google Scholar's
  phrase syntax; Crossref's ``query.bibliographic`` takes free text and would
  match the quote characters themselves.
- Crossref dates a work by its publisher's ``issued`` stamp, which drifts from
  what a manuscript writes down, so nothing here rejects on a year. That is the
  identity rule's job and it has a measured tolerance.
- A record whose ``container-title`` is empty is passed through with an empty
  venue rather than dropped. Dropping it here would hide the reason from the
  identity rule, which rejects on an empty venue and reports it.

Field reference: https://api.crossref.org/swagger-ui/index.html
"""

from typing import Any
from urllib.parse import urlencode

from .identity import PublicationCandidate, ReferenceQuery
from .metadata_lookup import (
    ProviderResponse,
    default_user_agent,
    http_get_json,
    provider_response_for_failure,
)
from .title_matching import first_author_surname, normalize_doi

NAME = "crossref"
ENDPOINT = "https://api.crossref.org/works"

# Trims the response to the fields mapped below. Crossref documents ``select``
# as a bandwidth control, and these names have been stable for years.
SELECT = "DOI,title,author,issued,container-title,type,URL"


class CrossrefLookup:
    """The Crossref provider."""

    name = NAME

    def search(
        self,
        query: ReferenceQuery,
        *,
        limit: int = 10,
        timeout_seconds: float = 10,
    ) -> ProviderResponse:
        """Return Crossref's records for a reference. Never raises."""
        if not query.title.strip():
            # Crossref's bibliographic query is a title query; without a title
            # there is nothing to ask, and asking would return noise.
            return ProviderResponse(status="ok", candidates=[])
        result = http_get_json(
            build_url(query, limit),
            timeout_seconds=timeout_seconds,
            user_agent=default_user_agent(),
        )
        if result.body is None:
            return provider_response_for_failure(result, error_prefix="CROSSREF")
        return ProviderResponse(status="ok", candidates=map_items(result.body))


def build_url(query: ReferenceQuery, limit: int) -> str:
    """Return the Crossref request URL for a reference."""
    params = {
        "query.bibliographic": bibliographic_query(query),
        "rows": str(limit),
        "select": SELECT,
    }
    return f"{ENDPOINT}?{urlencode(params)}"


def bibliographic_query(query: ReferenceQuery) -> str:
    """Return the free-text query: the title, plus the first author's surname."""
    surname = first_author_surname(query.authors)
    return " ".join(part for part in (query.title.strip(), surname) if part)


def map_items(body: Any) -> list[PublicationCandidate]:
    """Map a Crossref response body onto candidates, skipping unusable items."""
    if not isinstance(body, dict):
        return []
    message = body.get("message")
    if not isinstance(message, dict):
        return []
    items = message.get("items")
    if not isinstance(items, list):
        return []
    return [candidate for candidate in (map_item(item) for item in items) if candidate is not None]


def map_item(item: Any) -> PublicationCandidate | None:
    """Map one Crossref work onto a candidate, or None if it has no identifier."""
    if not isinstance(item, dict):
        return None
    doi = normalize_doi(_text(item.get("DOI")))
    url = _text(item.get("URL"))
    record_id = doi or url
    if not record_id:
        return None
    return PublicationCandidate(
        provider=NAME,
        record_id=record_id,
        title=_first_text(item.get("title")),
        authors=_authors(item.get("author")),
        year=_issued_year(item.get("issued")),
        venue=_first_text(item.get("container-title")),
        kind=_text(item.get("type")),
        doi=doi,
        url=url,
        # A deposited manuscript or a preprint server posting is not the same
        # claim on a work as a published record, so it loses a same-work tie.
        is_repository=_text(item.get("type")) == "posted-content",
    )


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _first_text(value: Any) -> str:
    """Return the first non-empty string of a Crossref list-valued field."""
    if isinstance(value, list):
        for entry in value:
            text = _text(entry)
            if text:
                return text
        return ""
    return _text(value)


def _authors(value: Any) -> list[str]:
    """Return authors in ``"Family, Given"`` form, which the surname reader expects."""
    if not isinstance(value, list):
        return []
    authors = []
    for entry in value:
        if not isinstance(entry, dict):
            continue
        family = _text(entry.get("family"))
        given = _text(entry.get("given"))
        if family and given:
            authors.append(f"{family}, {given}")
        elif family:
            authors.append(family)
        else:
            # Organisational contributors carry a single ``name`` field.
            name = _text(entry.get("name"))
            if name:
                authors.append(name)
    return authors


def _issued_year(value: Any) -> int | None:
    """Return the year of a Crossref date, which is ``[[year, month, day]]``."""
    if not isinstance(value, dict):
        return None
    parts = value.get("date-parts")
    if not isinstance(parts, list) or not parts:
        return None
    first = parts[0]
    if not isinstance(first, list) or not first:
        return None
    year = first[0]
    return year if isinstance(year, int) else None
