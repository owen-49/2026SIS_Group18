"""Query OpenAlex for a cited reference.

OpenAlex is the primary provider in the chain: it indexes preprints and
conference papers that Crossref covers thinly or not at all, which is where
several references in the manuscript set actually live.

Design notes:
- The query carries the title only. Measured: sending the author name as well
  pushes the correct record out of the first six results, degrading the search
  to a bag-of-words match. Crossref wants the opposite, so the two providers
  build their queries differently and neither inherits the other's rule.
- The venue is read from ``primary_location``: ``source.display_name`` first and
  ``raw_source_name`` second. Both are required. The correct record for one
  reference has a null ``source`` and its venue only in ``raw_source_name``, so
  reading ``source`` alone would reject a correct answer.
- ``locations[]`` is never consulted, for any field. A hijacked record for
  "Attention Is All You Need" has null venues on its primary location and three
  arXiv entries in ``locations[]``; falling back would hand a fabricated record
  the venue that :func:`engine.identity.select_identity` uses to reject it.
- ``select`` is deliberately not used to trim the response, unlike the Crossref
  provider. OpenAlex has renamed response fields across versions (``title`` to
  ``display_name``), and selecting a renamed field yields null rather than an
  error -- which would silently empty a venue while the request still succeeded.
  The page size keeps the response bounded instead.

Field reference: https://docs.openalex.org/api-entities/works
"""

import os
from typing import Any
from urllib.parse import urlencode

from .identity import PublicationCandidate, ReferenceQuery
from .metadata_lookup import (
    CONTACT_ENV_VAR,
    ProviderResponse,
    default_user_agent,
    http_get_json,
    provider_response_for_failure,
)
from .title_matching import normalize_doi

NAME = "openalex"
ENDPOINT = "https://api.openalex.org/works"


class OpenAlexLookup:
    """The OpenAlex provider."""

    name = NAME

    def search(
        self,
        query: ReferenceQuery,
        *,
        limit: int = 10,
        timeout_seconds: float = 10,
    ) -> ProviderResponse:
        """Return OpenAlex's records for a reference. Never raises."""
        if not query.title.strip():
            return ProviderResponse(status="ok", candidates=[])
        result = http_get_json(
            build_url(query, limit),
            timeout_seconds=timeout_seconds,
            user_agent=default_user_agent(),
        )
        if result.body is None:
            return provider_response_for_failure(result, error_prefix="OPENALEX")
        return ProviderResponse(status="ok", candidates=map_items(result.body))


def build_url(query: ReferenceQuery, limit: int) -> str:
    """Return the OpenAlex request URL for a reference."""
    params = {
        "filter": f"title.search:{query.title.strip()}",
        "per-page": str(limit),
    }
    contact = os.getenv(CONTACT_ENV_VAR, "").strip()
    if contact:
        # OpenAlex routes requests carrying a contact address to its polite
        # pool. Sent as a parameter as well as in the User-Agent, because the
        # pool is chosen from the parameter.
        params["mailto"] = contact
    return f"{ENDPOINT}?{urlencode(params)}"


def map_items(body: Any) -> list[PublicationCandidate]:
    """Map an OpenAlex response body onto candidates, skipping unusable items."""
    if not isinstance(body, dict):
        return []
    results = body.get("results")
    if not isinstance(results, list):
        return []
    mapped = (map_item(item) for item in results)
    return [candidate for candidate in mapped if candidate is not None]


def map_item(item: Any) -> PublicationCandidate | None:
    """Map one OpenAlex work onto a candidate, or None if it has no identifier."""
    if not isinstance(item, dict):
        return None
    doi = normalize_doi(_text(item.get("doi")))
    url = _text(item.get("id"))
    record_id = url.rstrip("/").rsplit("/", 1)[-1]
    if not record_id:
        record_id = doi
    if not record_id:
        return None
    location = _dict(item.get("primary_location"))
    source = _dict(location.get("source"))
    venue = _text(source.get("display_name")) or _text(location.get("raw_source_name"))
    kind = _text(item.get("type"))
    if item.get("is_paratext") is True:
        # OpenAlex flags front matter, tables of contents and the like; its
        # ``type`` for those is not always one the deny-list knows.
        kind = "paratext"
    return PublicationCandidate(
        provider=NAME,
        record_id=record_id,
        title=_text(item.get("title")) or _text(item.get("display_name")),
        authors=_authors(item.get("authorships")),
        year=_year(item.get("publication_year")),
        venue=venue,
        kind=kind,
        doi=doi,
        url=_text(location.get("landing_page_url")) or url,
        is_repository=_text(source.get("type")) == "repository",
    )


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _year(value: Any) -> int | None:
    return value if isinstance(value, int) else None


def _authors(value: Any) -> list[str]:
    """Return author display names, which OpenAlex gives as ``"Given Family"``."""
    if not isinstance(value, list):
        return []
    authors = []
    for entry in value:
        if not isinstance(entry, dict):
            continue
        name = _text(_dict(entry.get("author")).get("display_name"))
        if name:
            authors.append(name)
    return authors
