# Proposal: Replace Google Scholar Scraping with a Crossref Metadata Provider

**Owner proposed:** Engine / Scholar owner (Sichen)  
**Acceptance owner:** Siyuan  
**Status:** Proposal — requires team approval before implementation

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

## References

- Crossref REST API: https://support.crossref.org/hc/en-us/articles/214320426-REST-API
- Crossref REST API query parameters: https://github.com/CrossRef/rest-api-doc
- Google Scholar Search Help: https://scholar.google.com/intl/en/scholar/help.html
