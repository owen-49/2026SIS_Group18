"""Query metadata providers for a cited reference and decide its identity.

Provides the external "does this reference actually exist?" lookup used by the
bibliography Audit path, over documented REST APIs rather than a scraped
citation index. This module owns the chain: the providers know how to ask their
own API, and :func:`select_identity` alone decides whether any answer is the
cited work.

Design notes:
- The overall outcome has to distinguish "the sources do not have this work"
  from "we did not manage to ask". A provider that completes and finds nothing
  is negative evidence; a provider that is throttled or unreachable is no
  evidence at all, and mixing them would let a partial search be reported as a
  conclusion. So ``not_found`` is returned only when every provider completed
  and none of them identified the work; any failure among them yields
  ``failed``. The backend already enforces this from its side -- its
  ``LookupResult`` validator rejects ``not_found`` unless every attempt is
  itself ``not_found`` -- so the rule here is the same rule, applied where the
  attempts are made.
- ``ambiguous`` is not held to that standard, because it does not claim
  completeness: it hands the caller records to review. When some providers did
  not complete, the reason says so, so a reviewer knows the candidate set is
  partial rather than exhaustive.
- The chain stops at the first provider that lets the identity be settled.
  Measured: a reference resolvable from the first provider never reaches the
  second, which is the point of ordering them.
- ``rate_limited`` is this module's own vocabulary, not the backend's: the wire
  model has no such outcome. The backend adapter in
  ``backend/src/services/provider_chain_lookup.py`` maps it to
  ``outcome="failed"`` with an uppercase ``error_code``, so a throttle is never
  reported as an absent publication.
- Bounded worst case: each provider makes **one** request -- there is no retry
  loop, because neither API has a punitive backoff to wait out -- and
  ``timeout_seconds`` bounds each socket operation. It does not bound the whole
  exchange: a server that dribbles bytes can outlast it. The bibliography
  adapter that calls this therefore documents the bound -- one request per
  provider, so about two socket operations per reference -- rather than
  pretending to enforce a ceiling it cannot.
- A provider that raises is caught here rather than trusted to return a status,
  so one broken provider cannot take the audit down with it.
"""

import json
import os
import urllib.error
import urllib.request
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from .identity import (
    IdentityDecision,
    PublicationCandidate,
    ReferenceQuery,
    select_identity,
)

# Measured, not a default: the correct record for one reference in the
# manuscript set appeared at rank 9 of the provider's ranking, so a smaller page
# would have missed it. Relying on rank 1 is the same mistake as relying on a
# score threshold.
DEFAULT_CANDIDATE_LIMIT = 10

DEFAULT_TIMEOUT_SECONDS = 10

# Neither API pages a ten-record JSON response anywhere near this; the cap only
# exists so a broken or hostile server cannot stream without end.
MAX_RESPONSE_BYTES = 8 * 1024 * 1024

# Read from the environment rather than committed, so no personal address enters
# the repository. Crossref and OpenAlex both serve requests carrying a contact
# address from a faster, more reliable pool.
CONTACT_ENV_VAR = "CLAIMTRACE_CONTACT_MAILTO"


@dataclass
class ProviderResponse:
    """What one provider managed to do with one query."""

    status: str  # "ok" | "failed" | "rate_limited"
    candidates: list[PublicationCandidate] = field(default_factory=list)
    error_code: str | None = None
    error: str = ""


@dataclass
class ProviderAttempt:
    """One provider's turn in the chain, and what it left the decision at.

    Attributes:
        outcome: The identity decision once this provider's records had been
            added, so it describes the chain up to and including this provider
            rather than the provider alone. The first attempt reading ``found``
            is the one that settled the reference.
    """

    provider: str
    outcome: str  # "found" | "ambiguous" | "not_found" | "failed" | "rate_limited"
    error_code: str | None = None
    error: str = ""
    candidate_count: int = 0


@dataclass
class MetadataLookupResult:
    """The result of asking every provider about one reference."""

    outcome: str  # "found" | "ambiguous" | "not_found" | "failed" | "rate_limited"
    query: ReferenceQuery
    selected: PublicationCandidate | None = None
    rule: str = ""
    reason: str = ""
    candidates: list[PublicationCandidate] = field(default_factory=list)
    rejected: list[PublicationCandidate] = field(default_factory=list)
    attempts: list[ProviderAttempt] = field(default_factory=list)


@dataclass
class HttpResult:
    """The outcome of one HTTP request, including the failures."""

    status_code: int
    body: Any = None
    error: str = ""


class MetadataProvider(Protocol):
    """A source of bibliographic records.

    Implementations build their own query: the two APIs want different things,
    and one of them is measurably worse if given the author's name.
    """

    name: str

    def search(
        self,
        query: ReferenceQuery,
        *,
        limit: int,
        timeout_seconds: float,
    ) -> ProviderResponse:
        """Return this provider's records for a reference. Never raises."""
        ...


def default_user_agent() -> str:
    """Return the User-Agent to identify this client to the metadata APIs."""
    contact = os.getenv(CONTACT_ENV_VAR, "").strip()
    agent = "ClaimTrace/0.1 (bibliography audit; +https://github.com/owen-49/2026SIS_Group18)"
    return f"{agent} mailto:{contact}" if contact else agent


def http_get_json(
    url: str,
    *,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    user_agent: str = "",
    headers: dict[str, str] | None = None,
) -> HttpResult:
    """Fetch a JSON document over HTTP, converting every failure to a result.

    This is the only place the engine opens a socket. Errors are returned rather
    than raised, and an HTTP error status is reported as a result, so a caller
    can tell a missing record (404) from a throttled client (429) from an
    unparseable response without exception handling of its own.

    Args:
        url: The absolute URL to fetch.
        timeout_seconds: Per-socket-operation timeout.
        user_agent: The User-Agent header; callers should use
            :func:`default_user_agent`.
        headers: Extra request headers.

    Returns:
        An :class:`HttpResult`. ``status_code`` is 0 when no response arrived.
    """
    request = urllib.request.Request(  # noqa: S310 - both endpoints are https constants
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": user_agent or default_user_agent(),
            **(headers or {}),
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310
            status_code = int(response.status)
            payload = response.read(MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as exc:
        return HttpResult(status_code=int(exc.code), error=f"HTTP {exc.code} {exc.reason}")
    except urllib.error.URLError as exc:
        return HttpResult(status_code=0, error=f"request failed: {exc.reason}")
    except Exception as exc:  # timeout, TLS, a malformed response line
        return HttpResult(status_code=0, error=f"request failed: {exc}")

    if len(payload) > MAX_RESPONSE_BYTES:
        return HttpResult(status_code=status_code, error="response exceeded the size cap")
    try:
        return HttpResult(status_code=status_code, body=json.loads(payload))
    except ValueError as exc:
        return HttpResult(status_code=status_code, error=f"response was not JSON: {exc}")


def provider_response_for_failure(
    result: HttpResult,
    *,
    error_prefix: str,
) -> ProviderResponse:
    """Map a failed request onto a provider response.

    The providers share this because the cases are the same for both APIs, and
    the distinction between them is the whole point: a throttle is not a
    failure to retry blindly, and a 404 is an answer rather than an error.
    """
    if result.status_code == 429:
        return ProviderResponse(
            status="rate_limited",
            error_code=f"{error_prefix}_RATE_LIMITED",
            error=result.error,
        )
    if result.status_code == 404:
        # The API answered the query; it simply holds no such record. That is
        # negative evidence like any other empty result.
        return ProviderResponse(status="ok", candidates=[])
    if result.status_code == 0:
        code = f"{error_prefix}_TRANSPORT"
    elif result.status_code == 200:
        code = f"{error_prefix}_UNREADABLE_BODY"
    else:
        code = f"{error_prefix}_HTTP_{result.status_code}"
    return ProviderResponse(status="failed", error_code=code, error=result.error)


def lookup_reference(
    query: ReferenceQuery,
    providers: Sequence[MetadataProvider],
    *,
    limit: int = DEFAULT_CANDIDATE_LIMIT,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> MetadataLookupResult:
    """Ask each provider in turn and decide whether the reference is identified.

    Providers are queried in the order given and the chain stops as soon as the
    accumulated records settle the identity, so a reference the first provider
    resolves costs one request.

    Args:
        query: The reference as the manuscript gives it.
        providers: The providers to consult, most authoritative first. Must not
            be empty; a lookup with nowhere to look is a configuration error and
            returns ``failed`` with no attempts.
        limit: Maximum records to request from each provider.
        timeout_seconds: Per-socket-operation timeout for each request.

    Returns:
        A :class:`MetadataLookupResult`. Never raises.
    """
    if not providers:
        return MetadataLookupResult(
            outcome="failed",
            query=query,
            reason="No metadata providers are configured, so nothing was searched.",
        )

    attempts: list[ProviderAttempt] = []
    collected: list[PublicationCandidate] = []
    completed = 0
    failed = 0
    throttled = 0

    for provider in providers:
        name = getattr(provider, "name", "") or type(provider).__name__
        try:
            response = provider.search(query, limit=limit, timeout_seconds=timeout_seconds)
        except Exception as exc:  # a provider must not take the chain down
            attempts.append(
                ProviderAttempt(
                    provider=name,
                    outcome="failed",
                    error_code="PROVIDER_RAISED",
                    error=f"{name} raised {type(exc).__name__}: {exc}",
                )
            )
            failed += 1
            continue

        if response.status == "rate_limited":
            attempts.append(
                ProviderAttempt(
                    provider=name,
                    outcome="rate_limited",
                    error_code=response.error_code or "RATE_LIMITED",
                    error=response.error,
                    candidate_count=len(response.candidates),
                )
            )
            throttled += 1
            continue

        if response.status != "ok":
            attempts.append(
                ProviderAttempt(
                    provider=name,
                    outcome="failed",
                    error_code=response.error_code or "PROVIDER_FAILED",
                    error=response.error,
                    candidate_count=len(response.candidates),
                )
            )
            failed += 1
            continue

        collected.extend(response.candidates)
        completed += 1
        decision = select_identity(query, collected)
        attempts.append(
            ProviderAttempt(
                provider=name,
                outcome=decision.status,
                candidate_count=len(response.candidates),
                error=decision.reason,
            )
        )
        if decision.status == "found":
            return _result_from_decision(
                "found", query, decision, attempts, selected=decision.selected
            )

    decision = select_identity(query, collected)
    incomplete = _incomplete_note(failed, throttled)

    if decision.status == "ambiguous":
        return _result_from_decision("ambiguous", query, decision, attempts, extra=incomplete)
    if failed:
        return MetadataLookupResult(
            outcome="failed",
            query=query,
            reason=(
                f"{failed} provider(s) did not complete, so the search is inconclusive"
                f"{incomplete}{_decision_note(decision)}"
            ),
            candidates=decision.candidates,
            rejected=[item.candidate for item in decision.rejected],
            attempts=attempts,
        )
    if completed == 0:
        return MetadataLookupResult(
            outcome="rate_limited",
            query=query,
            reason=f"Every provider refused the request{incomplete}",
            attempts=attempts,
        )
    if throttled:
        # A throttled provider is no evidence at all, so a reference the others
        # happened not to find is not "not found" -- it is a partial search, and
        # this module does not report a partial search as a conclusion. The same
        # rule that sends a transport failure to ``failed`` above. The backend
        # enforces it from its side too: its ``LookupResult`` validator rejects
        # ``not_found`` unless every attempt is itself ``not_found``, and a
        # ``rate_limited`` attempt has no such spelling on the wire.
        return MetadataLookupResult(
            outcome="failed",
            query=query,
            reason=(
                f"{throttled} provider(s) were rate-limited, so the search is inconclusive"
                f"{_decision_note(decision)}"
            ),
            candidates=decision.candidates,
            rejected=[item.candidate for item in decision.rejected],
            attempts=attempts,
        )
    return _result_from_decision("not_found", query, decision, attempts)


def _result_from_decision(
    outcome: str,
    query: ReferenceQuery,
    decision: IdentityDecision,
    attempts: list[ProviderAttempt],
    *,
    selected: PublicationCandidate | None = None,
    extra: str = "",
) -> MetadataLookupResult:
    return MetadataLookupResult(
        outcome=outcome,
        query=query,
        selected=selected or decision.selected,
        rule=decision.rule,
        reason=f"{decision.reason}{extra}",
        candidates=decision.candidates,
        rejected=[item.candidate for item in decision.rejected],
        attempts=attempts,
    )


def _incomplete_note(failed: int, throttled: int) -> str:
    parts = []
    if failed:
        parts.append(f"{failed} failed")
    if throttled:
        parts.append(f"{throttled} was rate-limited")
    if not parts:
        return ""
    return f" ({', '.join(parts)}; some sources were not searched)"


def _decision_note(decision: IdentityDecision) -> str:
    if decision.status == "not_found":
        return ""
    return f"; the records returned so far leave it {decision.status}"
