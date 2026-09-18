# Proposal: Replace Google Scholar Scraping with a Crossref Metadata Provider

**Owner proposed:** Engine / Scholar owner (Sichen)  
**Acceptance owner:** Siyuan  
**Status:** **Implemented, with the deviations in §8.** The proposal below is kept
as written, because it is the record of what was proposed and why. Read §8 for
what was actually built and where it differs — in particular, the weighted score
in §3 was not used, and Crossref is not the only provider.

## 1. Evidence from the current implementation

The latest `main` includes PR #33 (`backend/scholar-worker-deadline`). The live Audit workflow now ends each Scholar worker after its own 25-second deadline and preserves the worker log.

When a real PDF was audited locally, the worker repeatedly reported:

```text
INFO scholarly: Got a captcha request.
INFO scholarly: Solving the captcha took already 10 seconds
```

The Audit response safely returned `LOOKUP_FAILED`; it did not claim that the publications were absent. This fixes the former opaque 30-second timeout, but Google Scholar scraping remains unable to provide reliable live metadata because automated requests are challenged with CAPTCHA.

## 2. Goal

Replace the `scholarly` / Google Scholar scraping path with one approved, programmatic metadata source: **Crossref REST API**.

Crossref supports DOI metadata retrieval and bibliographic lookup through a public REST API. The implementation must never treat the first search result as an identified paper. It must preserve the existing Audit v2 contract and its conservative status meanings.

## 3. Proposed architecture

```text
Audit route
  -> CrossrefBibliographyLookup (backend adapter)
  -> CrossrefLookup (Engine provider)
  -> Crossref REST API
  -> existing LookupResult / Audit v2 comparison and persistence
```

### Engine changes

Add:

```text
engine/engine/metadata_lookup.py
engine/engine/crossref_lookup.py
engine/tests/test_crossref_lookup.py
```

`metadata_lookup.py` defines provider-neutral value objects:

```python
PublicationCandidate(provider, record_id, url, title, authors, year, venue, doi)
MetadataLookupOutcome(status, candidates, error)
```

`CrossrefLookup.resolve(reference)` performs the following:

1. **DOI present:** normalize the DOI and call `GET /works/{doi}`. Only an exact normalized DOI match returns `found`.
2. **No DOI:** call `GET /works?query.bibliographic={title+author+year}&rows=10`.
3. Normalize titles using NFKC, case folding, punctuation removal, and de-hyphenation of PDF line wraps.
4. Score each candidate: exact title 0.75, first-author surname match 0.15, exact year 0.10.
5. Return `found` only when the best candidate scores at least 0.90 and leads the second candidate by at least 0.08.
6. Return `ambiguous` when close candidates cannot be safely distinguished; return `not_found` only after a completed query has no acceptable candidate.
7. Return `failed` for timeouts, network errors, HTTP 429, and 5xx responses.

The provider uses a five-second connect/read timeout, at most one retry for transient network or 5xx failures, and no retry loop for HTTP 429. Requests identify ClaimTrace and a maintained contact email through `User-Agent` and `mailto`.

### Backend changes

Add `CrossrefBibliographyLookup` under `backend/src/services/`. It converts Engine candidates into the existing `LookupResult` and `ExternalRecord` structures:

```text
provider: crossref
record_id: doi:<normalized DOI>
url: https://doi.org/<normalized DOI>
```

Replace `BoundedScholarLookup` as the configured bibliography lookup in `backend/src/main.py`. The API response shape, `contract_version: 2`, report persistence, and frontend types remain unchanged.

## 4. Required status mapping

| Provider outcome | Audit status | Meaning |
|---|---|---|
| Exact, uniquely identified record | `VERIFIED` or `METADATA_MISMATCH` | Identity is established; fields are compared. |
| Similar candidates without a safe winner | `NEEDS_REVIEW` | The user chooses or verifies manually. |
| Completed Crossref query, no acceptable candidate | `NOT_FOUND` | The configured source found no acceptable record; this is not a fabrication claim. |
| Timeout, 429, 5xx, or network error | `LOOKUP_FAILED` | Publication existence remains unchecked. |

## 5. Required tests and acceptance evidence

1. Exact DOI resolution and field comparison.
2. A Crossref result list where rank one is wrong and rank two is correct.
3. Two close candidates producing `NEEDS_REVIEW`, never an arbitrary selection.
4. A completed zero-result query producing `NOT_FOUND`.
5. Timeout, HTTP 429, and HTTP 5xx producing `LOOKUP_FAILED`.
6. Duplicate references in one Audit triggering one provider request through request-scoped caching.
7. Persisted Audit retrieval after a new application lifespan and a new HTTP process.
8. Live BibTeX and PDF acceptance with a DOI success case, an ambiguous case, and a provider-failure case.

## 6. Scope and rollout

This is a separate feature PR, for example `engine/crossref-metadata-provider`. It must not be added to the PR #33 timeout hardening change.

Initial rollout uses Crossref as the only external provider. If Crossref lacks coverage for a citation, the result stays conservative. Adding a second provider later requires a separate evaluation and PR; it must not silently change identity selection rules.

## 7. Decision requested

Please confirm:

1. Crossref is approved as the sole programmatic metadata source for the next implementation.
2. Sichen owns the Engine provider and backend adapter.
3. Siyuan will run and document the acceptance cases above after the implementation PR is ready.

## 8. Outcome — what was built instead

The goal in §2 was met. The design in §3 was not, in two ways that were decided
during implementation and are worth knowing before reading this proposal as a
description of the system:

**Identity is decided structurally, not by a weighted score.** §3 step 4-5
proposed scoring each candidate (exact title 0.75, surname 0.15, year 0.10) and
accepting above 0.90 with a 0.08 lead. That was not built, because a score
threshold conflates two different questions — "is this the same work?" and "how
confident are we?" — and cannot be tuned honestly without a labelled set. What
was built instead is `engine/identity.py::select_identity`: a sequence of hard
tiers (normalised DOI, arXiv id, exact title, then title-and-year-and-venue
agreement) that either settle the identity or refuse to. A record that fails a
tier is *rejected*, and the rejection is reported, rather than being down-weighted
and possibly still selected. Two measured rules fall out of this and are
deliberate, not incidental:

- A candidate with no venue is rejected. This is the anti-fabrication rule, and
  it costs real coverage — see §8.1.
- `abs(reference_year - candidate_year) > 1` rejects. The tolerance is 1 because
  0 rejects correct IEEE-style references; it is measured, not chosen.

**Two providers, not one.** §6 said a second provider would need its own
evaluation and PR. That evaluation happened, and the result is the chain in
`engine/metadata_lookup.py`: **OpenAlex first, then Crossref**. OpenAlex is
primary because it indexes the preprints that reference lists cite alongside the
published form, and because it resolves records whose venue survives only in
`raw_source_name`. The chain short-circuits at the first provider that settles a
reference, so a reference OpenAlex resolves never reaches Crossref — measured at
one request and about 1.5 s per resolvable reference.

**Names as built:**

| Proposed (§3) | Built |
|---|---|
| `CrossrefBibliographyLookup` | `backend/src/services/provider_chain_lookup.py::ProviderChainLookup` |
| `CrossrefLookup.resolve(reference)` | `OpenAlexLookup.search` / `CrossrefLookup.search`, over `lookup_reference(query, providers)` |
| `MetadataLookupOutcome(status, candidates, error)` | `MetadataLookupResult(outcome, query, selected, rule, reason, candidates, rejected, attempts)` |
| `record_id: doi:<DOI>` | `<provider>:<record id>`, e.g. `openalex:W2963404627` |

**Removed:** `backend/src/services/google_scholar_lookup.py`,
`bounded_scholar_lookup.py`, `scholar_worker.py`, `engine/engine/scholar_search.py`,
and the `scholarly` and `bibtexparser` dependencies. There is no Scholar fallback,
no worker subprocess, and no minimum interval between lookups — the providers are
documented REST APIs queried once each, and a throttle would have nothing to
protect against. The `SCHOLAR_*` environment variables are gone; the only bound
is `METADATA_LOOKUP_TIMEOUT_SECONDS` (per socket operation).

**Acceptance (§5) as actually run:** the cases live in
`backend/scripts/audit_live_acceptance.py`, which runs the real Parser, provider,
mapper, identity rules, adapter, comparison and storage, replacing only the bytes
each HTTP request receives. Two of the proposed cases changed shape: duplicate
references in one audit are *not* request-cached (each is looked up; the chain is
sequential and the cost is bounded), and the "rank one is wrong, rank two is
correct" case is now covered by the identity tiers rather than by score ordering.
The remaining cases — DOI resolution, ambiguous candidates, zero-result, timeout,
429 and 5xx — are all present. `DEFAULT_CANDIDATE_LIMIT` is 10 because a correct
record was measured at rank 9.

### 8.1 Known coverage cost

A reference whose only candidate records carry no venue now reports `NOT_FOUND`,
where Scholar would have returned a hit. This is the anti-fabrication rule doing
what it was designed to do, and it is a real cost rather than a bug — do not
"fix" it by relaxing the venue requirement or `NON_PUBLICATION_KINDS` without a
measurement showing what the relaxation admits.

The live acceptance fixture is the clearest example, and it is a famous paper:
OpenAlex holds "Attention Is All You Need" (Vaswani et al.) as a single venue-less
preprint record, so both the venue rule and the year rule reject it and the audit
reports `NOT_FOUND`. The reason string names the rule that fired. The control
fixture reaches `VERIFIED` because it supplies a record with a venue and a
matching year — controlled mode pins which code paths are reached, live mode
shows what the sources actually hold, and the two are expected to differ.

## References

- Crossref REST API: https://support.crossref.org/hc/en-us/articles/214320426-REST-API
- Crossref REST API query parameters: https://github.com/CrossRef/rest-api-doc
- Google Scholar Search Help: https://scholar.google.com/intl/en/scholar/help.html
