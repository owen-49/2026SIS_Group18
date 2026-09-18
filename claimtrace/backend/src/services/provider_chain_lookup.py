"""Adapt the Engine's metadata provider chain to the bibliography lookup contract.

The Engine owns the question "is this reference the work it names?" -- it builds
the query, asks its providers, and decides identity structurally
(:func:`engine.identity.select_identity`) rather than by a weighted score. This
module owns only the translation into the Audit v2 wire model, and it exists
because that model enforces three invariants the Engine has no reason to know
about:

- ``found`` requires exactly one record;
- ``ambiguous`` requires at least one;
- ``not_found`` requires that every lookup attempt is itself ``not_found``.

The first two are handled by dropping records that cannot be represented. The
third is the one that matters: the Engine's ``rate_limited`` outcome has no
spelling in the wire model's outcome literal, and a naive mapping would produce
a ``not_found`` carrying a ``failed`` attempt -- which the model rejects, and
which the audit service's broad ``except`` would then flatten into
``LOOKUP_FAILED``, losing the real cause. So a ``not_found`` is downgraded to
``failed`` here when any attempt says the search did not complete, and the
Engine applies the same rule at the source.

Design notes:
- **Bound.** Each provider makes exactly one request with no retry loop, and
  ``timeout_seconds`` bounds each socket operation rather than the whole
  exchange, so one reference costs about two socket operations. That is half
  the ceiling the deleted Scholar subprocess enforced (30s), which is why no new
  deadline mechanism replaces it: a blocking socket call can be abandoned but
  not cancelled, so a thread and a ``future.result(timeout=)`` would leak a
  thread and buy nothing the socket timeout does not already give. A server that
  dribbles bytes across reads can still outlast the bound, and this is stated
  rather than hidden.
- **No throttle.** The providers are documented REST APIs reached with a polite
  ``User-Agent``, the chain short-circuits at the first provider that settles a
  reference, and the audit loop is sequential. The Scholar path's minimum
  interval existed because scraping Google Scholar returns 429 on bursts; that
  evidence does not transfer.
- **A record without a URL is not reported.** The wire model requires an
  absolute http(s) URL, and the providers can return a record whose DOI is the
  only identifier it carries. The DOI resolver link is used, because it is the
  work's own identifier rather than a substitute; a candidate with neither is
  dropped and counted, and never replaced by a provider homepage or by a URL
  guessed from the record id.
- **``failed`` carries no records.** The frontend renders candidates under
  "Similar publications" whenever no record matched, so a lookup that failed
  with a candidate list would contradict its own status. The count goes in the
  reason instead.
- Never raises: a failure here is reported as ``failed`` with a code, so an
  audit degrades rather than aborting.
"""

import logging
from collections.abc import Sequence
from datetime import UTC, datetime
from urllib.parse import urlsplit

from engine.identity import PublicationCandidate
from engine.metadata_lookup import (
    DEFAULT_CANDIDATE_LIMIT,
    DEFAULT_TIMEOUT_SECONDS,
    MetadataLookupResult,
    MetadataProvider,
    ProviderAttempt,
    lookup_reference,
)

from ..audit_models import (
    BibliographicMetadata,
    ExternalRecord,
    LookupAttempt,
    LookupResult,
    ReferenceEntry,
)
from .reference_query import reference_query_for

logger = logging.getLogger(__name__)

# The provider name used for attempts this adapter synthesizes itself, so a
# reader can tell them from the ones a provider reported.
CHAIN_PROVIDER = "metadata_providers"

NO_PROVIDERS_CODE = "NO_PROVIDERS_CONFIGURED"
NO_TITLE_CODE = "NO_SEARCHABLE_TITLE"
NO_URL_CODE = "RECORD_URL_UNAVAILABLE"
INCOMPLETE_CODE = "PROVIDER_INCOMPLETE"
ADAPTER_FAILED_CODE = "LOOKUP_ADAPTER_FAILED"
RATE_LIMITED_CODE = "RATE_LIMITED"
PROVIDER_FAILED_CODE = "PROVIDER_FAILED"


def default_providers() -> list[MetadataProvider]:
    """Return the production chain, most authoritative first."""
    from engine.crossref_lookup import CrossrefLookup
    from engine.openalex_lookup import OpenAlexLookup

    # OpenAlex first because it is the one that resolves a reference whose
    # venue only survives in a raw source name, and because OpenAlex indexes
    # the preprints that the reference lists cite alongside the published form.
    return [OpenAlexLookup(), CrossrefLookup()]


class ProviderChainLookup:
    """Bibliography lookup over the Engine's provider chain."""

    def __init__(
        self,
        providers: Sequence[MetadataProvider],
        *,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        limit: int = DEFAULT_CANDIDATE_LIMIT,
    ) -> None:
        self._providers = list(providers)
        self._timeout_seconds = timeout_seconds
        self._limit = limit

    def lookup(self, entry: ReferenceEntry) -> LookupResult:
        """Resolve one reference against the provider chain. Never raises.

        A ``not_found`` is emitted only when every provider completed and none
        of them identified the work; a throttled or failed provider turns the
        same situation into ``failed``, because a partial search is not a
        conclusion about the reference.
        """
        try:
            return self._lookup(entry)
        except Exception as exc:  # this module's own faults stay traceable to it
            logger.exception("Metadata provider lookup failed for entry %s", entry.entry_id)
            return _failed(f"{type(exc).__name__}: {exc}", ADAPTER_FAILED_CODE)

    def _lookup(self, entry: ReferenceEntry) -> LookupResult:
        query = reference_query_for(entry)
        if not query.title.strip():
            # The audit service short-circuits an unsearchable reference before
            # reaching here, so this is the second line rather than the first.
            # A reference with no title was not searched, which is not the same
            # answer as a reference that was searched and not found.
            return _failed(
                "The reference has no searchable title, so no source was queried.",
                NO_TITLE_CODE,
            )
        if not self._providers:
            return _failed(
                "No metadata providers are configured, so nothing was searched.",
                NO_PROVIDERS_CODE,
            )
        result = lookup_reference(
            query,
            self._providers,
            limit=self._limit,
            timeout_seconds=self._timeout_seconds,
        )
        return _to_lookup_result(result)


def _to_lookup_result(result: MetadataLookupResult) -> LookupResult:
    """Translate one chain result into the audit wire model."""
    if not result.attempts:
        # The chain was handed nothing to search with. That is a configuration
        # error and says nothing about the reference, so it is reported as a
        # failure with a code rather than as a conclusion.
        return _failed(result.reason, NO_PROVIDERS_CODE)

    attempts = _attempts_for(result)
    retrieved_at = datetime.now(UTC)

    if result.outcome == "found":
        record = _record_for(result.selected, retrieved_at)
        if record is None:
            # The identity rule selected a record the wire model cannot carry.
            # Reporting it as found would mean emitting a source with no
            # location; reporting not_found would be a lie, since records came
            # back. Neither is worth it, so the lookup says it failed.
            return _failed(
                "The identified record carries no usable URL, so it cannot be "
                "reported as a source.",
                NO_URL_CODE,
                attempts=attempts,
            )
        return LookupResult(
            outcome="found",
            records=[record],
            attempts=attempts,
            reason=_reason(result),
        )

    if result.outcome == "ambiguous":
        records, dropped = _records_for(result.candidates, retrieved_at)
        if not records:
            return _failed(
                f"All {dropped} candidate record(s) carry no usable URL, so none can "
                "be offered for review.",
                NO_URL_CODE,
                attempts=attempts,
            )
        return LookupResult(
            outcome="ambiguous",
            records=records,
            attempts=attempts,
            reason=_reason(result, _dropped_note(dropped)),
        )

    if result.outcome == "not_found":
        incomplete = [attempt for attempt in attempts if attempt.outcome != "not_found"]
        if incomplete:
            return _failed(
                "The search did not complete at every source, so the reference's "
                "absence is not established.",
                incomplete[0].error_code or INCOMPLETE_CODE,
                attempts=attempts,
            )
        return LookupResult(
            outcome="not_found",
            records=[],
            attempts=attempts,
            reason=result.reason,
        )

    # The Engine's remaining outcomes are "failed" and "rate_limited"; both mean
    # the search did not complete, and neither is a statement about the work.
    return _failed(result.reason, _code_for(result), attempts=attempts)


def _attempts_for(result: MetadataLookupResult) -> list[LookupAttempt]:
    """Map the chain's attempts, synthesizing one if it reported none.

    The wire model requires at least one attempt. The case that reaches this is
    handled before it, so the synthesis here is a second line rather than a
    path of its own.
    """
    if not result.attempts:
        return [
            LookupAttempt(
                provider=CHAIN_PROVIDER,
                outcome="failed",
                error_code=INCOMPLETE_CODE,
                detail=result.reason,
            )
        ]
    return [_attempt_for(attempt) for attempt in result.attempts]


def _attempt_for(attempt: ProviderAttempt) -> LookupAttempt:
    if attempt.outcome == "rate_limited":
        # The wire model's outcome literal has no "rate_limited"; it is a way
        # of failing, and the code and detail keep the distinction readable.
        return LookupAttempt(
            provider=attempt.provider,
            outcome="failed",
            error_code=attempt.error_code or RATE_LIMITED_CODE,
            detail=_throttled_detail(attempt.error),
        )
    return LookupAttempt(
        provider=attempt.provider,
        outcome=attempt.outcome,
        error_code=attempt.error_code or None,
        detail=attempt.error,
    )


def _throttled_detail(error: str) -> str:
    note = "The provider rate-limited the request; retry later."
    return f"{note} {error}".strip() if error else note


def _records_for(
    candidates: Sequence[PublicationCandidate], retrieved_at: datetime
) -> tuple[list[ExternalRecord], int]:
    """Map the candidates, and count the ones that had to be dropped."""
    records = []
    dropped = 0
    for candidate in candidates:
        record = _record_for(candidate, retrieved_at)
        if record is None:
            dropped += 1
            continue
        records.append(record)
    return records, dropped


def _record_for(
    candidate: PublicationCandidate | None, retrieved_at: datetime
) -> ExternalRecord | None:
    """Build the wire record, or None when the candidate cannot be located."""
    if candidate is None:
        return None
    url = _url_for(candidate)
    if not url:
        return None
    return ExternalRecord(
        provider=candidate.provider,
        # Qualified by the provider so the id stays traceable on its own: the
        # two providers number their records independently, and the UI renders
        # this string next to the provider name.
        record_id=f"{candidate.provider}:{candidate.record_id}",
        url=url,
        retrieved_at=retrieved_at,
        metadata=BibliographicMetadata(
            title=candidate.title,
            authors=list(candidate.authors),
            year=candidate.year,
            venue=candidate.venue,
            doi=candidate.doi,
        ),
    )


def _url_for(candidate: PublicationCandidate) -> str:
    """Return the candidate's own location, its DOI resolver link, or nothing."""
    url = (candidate.url or "").strip()
    if _is_http_url(url):
        return url
    doi = (candidate.doi or "").strip()
    if doi:
        return f"https://doi.org/{doi}"
    return ""


def _is_http_url(value: str) -> bool:
    parsed = urlsplit(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _code_for(result: MetadataLookupResult) -> str:
    """Return the error code of the attempt that best explains the failure.

    A ``failed`` outcome can come from a provider that broke or from one that
    was throttled while the rest completed, so both kinds of attempt carry a
    code worth reporting; the transport failure is named first because it is
    the one a reader can act on.
    """
    if result.outcome == "rate_limited":
        return _first_code(result.attempts, "rate_limited", RATE_LIMITED_CODE)
    return (
        _first_code(result.attempts, "failed", "")
        or _first_code(result.attempts, "rate_limited", "")
        or PROVIDER_FAILED_CODE
    )


def _first_code(attempts: Sequence[ProviderAttempt], outcome: str, default: str) -> str:
    for attempt in attempts:
        if attempt.outcome == outcome and attempt.error_code:
            return attempt.error_code
    return default


def _reason(result: MetadataLookupResult, extra: str = "") -> str:
    """Compose the sentence the audit report shows for this reference."""
    parts = [result.reason] if result.reason else []
    if result.outcome == "found" and result.rule:
        # The rule is not on the wire anywhere else, and it is the thing
        # engine.identity keeps in order to answer "which tier decided this?".
        parts.append(f"(matched by {result.rule})")
    if extra:
        parts.append(extra)
    return " ".join(parts)


def _dropped_note(dropped: int) -> str:
    if not dropped:
        return ""
    return f"{dropped} candidate(s) were dropped for carrying no usable URL."


def _failed(
    reason: str,
    error_code: str,
    *,
    attempts: Sequence[LookupAttempt] | None = None,
) -> LookupResult:
    """Build a failure result, with an attempt that names the reason.

    Passing ``attempts`` reports what each provider did. The failure this
    function is reporting is then the adapter's own decision rather than a
    provider's -- an identified record with nowhere to point, say -- so the
    attempt naming it is appended instead of replacing them. Without it the
    report would read ``failed`` beside an attempt that succeeded, with nothing
    to explain the difference.
    """
    reported = list(attempts) if attempts is not None else []
    reported.append(
        LookupAttempt(
            provider=CHAIN_PROVIDER,
            outcome="failed",
            error_code=error_code,
            detail=reason,
        )
    )
    return LookupResult(
        outcome="failed",
        records=[],
        attempts=reported,
        reason=reason,
    )
