"""Query OpenAlex for a cited reference.

OpenAlex is the primary provider in the chain: it indexes preprints and
conference papers that Crossref covers thinly or not at all, which is where
several references in the manuscript set actually live.

Design notes:
- A reference carrying an identifier is asked for by identifier first; the
  title query runs only when that request completed and identified nothing.
  Measured: ``filter=doi:10.18653/v1/n19-1423`` returns the one record for that
  paper, and so does ``doi:10.48550/arxiv.1502.03167`` for a reference whose
  only identifier is an arXiv one. An exact lookup beats ranking on a phrase.
- An identifier the index does not hold is not evidence that the work is
  absent, so it does not end the search: the title query still runs. A failure
  does end it, because asking twice into a throttle spends the budget twice and
  learns nothing.
- What the fallback turns on is the provider's emptiness, not identity's
  verdict: a page of records the identity rules then reject is still this
  provider's answer about that identifier, and the title query is not asked on
  top of it. Identity is the layer above this one, and a provider that
  second-guessed it would be deciding whether a reference is the work -- the
  division this package is built on. Measured on the hijacked "Attention Is All
  You Need": the identifier query for that preprint's DOI returns one record,
  which the rules reject, and the title query returns that same record among
  ten, so asking both would spend two requests to be told the same thing.
- The title query carries the title only. Measured: sending the author name as
  well pushes the correct record out of the first six results, degrading the
  search to a bag-of-words match. Crossref wants the opposite, so the two
  providers build their queries differently and neither inherits the other's
  rule.
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
- The API key travels as an ``Authorization: Bearer`` header when one is
  configured, never as ``?api_key=``. OpenAlex serves both, but request URLs are
  logged: the live benchmark writes every URL it fetched into a report meant to
  be committed, so a key in the query string would be published with it.

Field reference: https://docs.openalex.org/api-entities/works
"""

import os
from typing import Any
from urllib.parse import urlencode

from .identity import PublicationCandidate, ReferenceQuery
from .metadata_lookup import (
    CONTACT_ENV_VAR,
    ProviderResponse,
    arxiv_doi,
    default_user_agent,
    doi_filter_value,
    http_get_json,
    provider_response_for_failure,
)
from .title_matching import normalize_doi

NAME = "openalex"
ENDPOINT = "https://api.openalex.org/works"

API_KEY_ENV_VAR = "OPENALEX_API_KEY"
"""Where an OpenAlex API key is read from, when the deployment has one.

Optional, and read here rather than through a backend setting, because the
provider client is the engine's -- the same arrangement as
:data:`engine.metadata_lookup.CONTACT_ENV_VAR`.

Without a key a request draws on a daily budget shared by every anonymous
client behind the same network address, which a corpus-sized audit run runs
out partway through. Measured on the 140-reference corpus: 70 requests
answered, then every remaining one answered ``429`` with a ``retry-after``
just under a day, leaving 91 requests unanswered and the run's verdicts
unusable. A free key multiplies that budget.
"""


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
        identifier = identifier_filter(query)
        title = query.title.strip()
        if not identifier and not title:
            return ProviderResponse(status="ok", candidates=[])
        if identifier:
            response = self._ask(build_identifier_url(query, limit), timeout_seconds)
            # Only an identifier request that completed and found nothing goes
            # on to the title query. A failure returns as it is: it is already
            # no evidence, and a second request into a throttle would only
            # spend the budget again.
            if response.candidates or response.status != "ok" or not title:
                return response
        return self._ask(build_url(query, limit), timeout_seconds)

    def _ask(self, url: str, timeout_seconds: float) -> ProviderResponse:
        """Return what one request to OpenAlex yielded. Never raises."""
        result = http_get_json(
            url,
            timeout_seconds=timeout_seconds,
            user_agent=default_user_agent(),
            headers=auth_headers(),
        )
        if result.body is None:
            return provider_response_for_failure(result, error_prefix="OPENALEX")
        return ProviderResponse(status="ok", candidates=map_items(result.body))


def auth_headers() -> dict[str, str]:
    """Return the headers that carry a configured API key, or none.

    Empty when no key is configured, which is a working configuration: the
    request is anonymous and OpenAlex answers it out of the shared daily
    budget. The value is stripped so that a line left blank in ``.env`` is no
    key at all rather than an empty bearer token.
    """
    key = os.getenv(API_KEY_ENV_VAR, "").strip()
    return {"Authorization": f"Bearer {key}"} if key else {}


def identifier_filter(query: ReferenceQuery) -> str:
    """Return the ``doi:`` filter for a reference that carries an identifier.

    The reference's own DOI when it has one, and otherwise the DOI arXiv
    registers for its arXiv identifier, which OpenAlex holds records under.
    Empty when the reference carries no identifier, or carries a DOI the filter
    grammar would misread.
    """
    return doi_filter_value(query.doi) or doi_filter_value(arxiv_doi(query.arxiv_id))


def build_url(query: ReferenceQuery, limit: int) -> str:
    """Return the OpenAlex request URL that asks a reference by title."""
    return _url(f"title.search:{query.title.strip()}", limit)


def build_identifier_url(query: ReferenceQuery, limit: int) -> str:
    """Return the OpenAlex request URL that asks a reference by identifier."""
    return _url(identifier_filter(query), limit)


def _url(filter_value: str, limit: int) -> str:
    params = {"filter": filter_value, "per-page": str(limit)}
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
