# Audit ↔ Engine metadata integration handoff

Owner: Siyuan (Audit integration)  
To: Sichen (Engine provider owner) and the backend team  
Purpose: hand off the live lookup blocker and confirm the Audit integration contract.

Baseline: current `origin/main` fetched on 2026-09-14, `ed5925c5`.
Branch and Draft PR: `backend/audit-live-acceptance`.

> ## Read this first — the blocker below is closed
>
> **2026-09-18.** The live lookup blocker this document was written to hand off
> is resolved: Google Scholar scraping is gone, replaced by the OpenAlex-then-Crossref
> provider chain (`backend/src/services/provider_chain_lookup.py`). The
> "External availability remains an explicit acceptance gap" line in Results was
> true when written and is not true now — the acceptance run reaches the real APIs
> and returns real records.
>
> **The committed JSON evidence under `controlled/` and `live/` is Scholar-era and
> is deliberately left unedited.** It carries `provider="google_scholar"` and
> `SCHOLAR_TIMEOUT`, and it records what actually happened at the time. Editing it
> would falsify a record; re-running the script overwrites it, so re-run into a
> scratch directory unless you intend to replace the evidence.
>
> The reproduction commands, the status expectations and the provider-specific
> limitations below have been updated to describe the current system; the narrative
> sections that describe the Scholar investigation are kept as history.

## Scope and fix

Verified upload -> completed Parser -> Scholar adapter/worker -> Audit v2
statuses and field differences -> disk persistence -> retrieval. Only production
change: startup now creates missing parents of UPLOAD_DIR. Before the fix, a fresh
`new-parent/uploads` configuration raised FileNotFoundError during FastAPI startup;
after it, startup and upload succeed. No search provider or matching algorithm added.

## Current handoff status

The Audit side is ready for integration. Parser completion, Audit status mapping,
metadata comparison, persistence, retrieval, timeout handling, and failure-state
mapping have been verified. The remaining handoff item was the live Scholar query:
the real BibTeX and PDF runs reached the worker deadline and returned
`LOOKUP_FAILED / SCHOLAR_TIMEOUT`.

**Resolved.** Sichen confirmed the deadline was hiding a blocked scrape rather than
a slow one, and the search provider was replaced rather than repaired — see
`../backend-audit-handoff- scholar- search.md` §8 for what was built. The Audit side
needed no contract change: the adapter translates the chain's outcomes into the same
`LookupResult`, and `contract_version` is still 2.

## Results

The bullets below describe the **current** run. Where a Scholar-era number is
retained it is marked as such, because the committed JSON records it.

- **Live run (current):** BibTeX and PDF both complete parsing and reach the real
  APIs. One provider request per reference, no retries. The reports persist and are
  retrieved unchanged through a new uvicorn process.
- **Live run (Scholar-era, as committed):** BibTeX returned SCHOLAR_TIMEOUT (30.25 s
  for upload/audit); PDF returned SCHOLAR_TIMEOUT for both entries (61.55 s total).
  This confirmed bounded failure handling, **not** successful live retrieval, and
  the acceptance gap it recorded is now closed.
- 200 backend tests and 336 Engine tests pass.
- Ruff passes for both packages.
- Controlled acceptance uses the real FastAPI lifespan/routes, the real BibTeX and
  PDF Parser, the real providers, the real response mappers, the real identity rules,
  the real adapter and the real Engine comparison. Only the bytes each provider's
  HTTP request receives are replaced, by `controlled_http_get_json`. It pins which
  code paths are reached; it is **not** live search success.
- BibTeX (controlled): `VERIFIED`, `NOT_FOUND`, `NOT_FOUND`, `LOOKUP_FAILED`,
  `LOOKUP_FAILED`, `LOOKUP_FAILED`.
- PDF (controlled): `NEEDS_REVIEW`, `NOT_FOUND`.
- Invalid PDF returns 415; missing or conflicting Audit inputs return 422.
- Both reports match their JSON files and GET responses, including retrieval over
  HTTP from a **new uvicorn process**, launched from the documented backend directory.

### What changed, and why the expectations changed with it

**The wrong-year fixture is no longer a field difference.** It used to reach the
comparison and be reported `METADATA_MISMATCH` with year "2020" against source
"2017". The identity rules now run *before* any comparison and reject the record
outright, because `abs(2020 - 2017) > YEAR_TOLERANCE` (1). The result is
`NOT_FOUND`, and because no record matched there are **no field checks at all** for
that entry. The rejection is pointed rather than silent: the reason reads
"20 of 20 records were ineligible (10 no venue, 10 year disagrees)".

**The provider failures name the provider and the cause.** A transport failure, an
HTTP 500 and an HTTP 429 for the same fixture produce
`OPENALEX_TRANSPORT`, `OPENALEX_HTTP_500` and `OPENALEX_RATE_LIMITED` respectively.
The chain then consults Crossref, which the fixtures also fail, so the overall
outcome is `LOOKUP_FAILED` — a failure is never reported as an absent publication.

**The controlled VERIFIED case depends on author spelling.** The fixture record
spells the author the way the BibTeX entry stores it ("Vaswani, A."), because
`VERIFIED` means field-for-field agreement and `compare_external_metadata`'s `exact`
gate compares normalised author lists element by element. The PDF fixture cites the
same work as "A. Vaswani" and lands in `NEEDS_REVIEW` instead. That difference is a
property of the reference's own author spelling, not of which provider answered.

## Reproduction

Install the repository backend, Parser and Engine dependencies and Java required
by OpenDataLoader. From `claimtrace/`, with the project's Python environment:

```sh
# write to a scratch directory unless you mean to replace the committed evidence
python backend/scripts/audit_live_acceptance.py --mode controlled --output /tmp/acceptance/controlled
python backend/scripts/audit_live_acceptance.py --mode live --output /tmp/acceptance/live
python -m pytest backend/tests/test_audit_startup.py backend/tests/test_bibliography_audit.py backend/tests/test_provider_chain_lookup.py backend/tests/test_bib_api.py engine/tests/test_metadata_lookup.py engine/tests/test_openalex_lookup.py engine/tests/test_crossref_lookup.py engine/tests/test_identity.py -q
```

The runner ignores developer .env, disables LLM credentials, selects this checkout's
Engine/Parser, and isolates all uploads in a temporary directory. No existing user
uploads are touched. Uvicorn is terminated on completion. Report IDs in committed
evidence belong to the removed temporary database; rerun to generate new IDs.

**Live mode** issues the real HTTP requests: one per provider per reference, no
retries, no spacing between references, bounded only by
`METADATA_LOOKUP_TIMEOUT_SECONDS` (per socket operation). It needs outbound network
access and will report `LOOKUP_FAILED` when there is none — that is a failure to
check, never a claim of absence.

**Controlled mode** replaces the bytes each provider's HTTP request receives, via
`controlled_http_get_json`. It patches `engine.openalex_lookup.http_get_json` and
`engine.crossref_lookup.http_get_json` — the names imported into each provider's
namespace — because patching `engine.metadata_lookup.http_get_json` instead would
leave both providers on the real network and the run would silently stop being
controlled. Everything else is production code. Its five fixtures are: a 200 with a
matching record (`found`), a 200 with an empty result list (absent), a 429
(throttled), a 500 (provider failure), and `status_code=0` (transport failure).
None of them is a production provider, and passing controlled mode is not evidence
that live retrieval works.

## Contract and limitations

- Upload via multipart `POST /api/parse`, field `file`; confirm `status=completed`
  (also checked through `GET /api/parse/{paper_id}`).
- Audit accepts exactly one of `bib_paper_id` / `manuscript_id`.
- POST `/api/audit` returns the completed report synchronously. GET
  `/api/audit/{audit_id}` reads persisted history, not background job progress.
- `contract_version=2`; reports include counts, results, warnings and status.
  Each result includes entry, field_checks, matched_record/candidates and lookup_attempts.
- NOT_FOUND requires a completed negative search; timeouts, HTTP failures, transport
  failures and rate limits stay LOOKUP_FAILED. Audit does not judge claim entailment
  and needs no source PDF uploads for a BibTeX input.
- PDF fixtures are synthetic, visually checked, with abbreviated author metadata
  and an intentionally duplicated title with a wrong year. They are not complete
  scholarly citations or a measurement of real lookup recall.
- Current Parser rejects a reference section with only one entry (requires two).
  The initial single-entry sample returned needs_review with zero results and a
  warning. This existing Parser boundary is documented, not changed in this PR.
- **The identity rules decide before any field comparison, and they are strict.**
  A wrong-year citation is rejected as *ineligible* rather than reported as a field
  difference, because `abs(reference_year - candidate_year) > YEAR_TOLERANCE` (1);
  the result is `NOT_FOUND` with no field checks. A candidate carrying no venue is
  rejected too — the anti-fabrication rule — which costs real coverage on
  venue-less preprint records (`../backend-audit-handoff- scholar- search.md` §8.1).
  Both are measured rules; relaxing either is a separate change needing its own
  measurement.
- **`VERIFIED` is field-for-field, and author spelling is part of it.**
  `compare_external_metadata`'s `exact` gate compares normalised author lists
  element by element, so the same work cited as "Vaswani, A." verifies while
  "A. Vaswani" does not. The Engine's own comparator tolerates that order
  difference; this gate does not. Widening the gate is deliberately out of scope
  here and needs its own measurement.
- **Query text comes from the reference, not only from its structured fields.**
  For a PDF reference the structured fields are usually empty and the title is
  recovered from the raw text; the audit service and the lookup share one function
  (`reference_query_for`) so they cannot disagree about what is searchable. A
  BibTeX block is never re-parsed as a reference-list entry — doing so recovers a
  corrupted DOI that would silently disable the identifier tier.
- No frontend/browser acceptance or changes are included. Draft status must remain
  until the team accepts the live-search evidence and any external availability limits.
