# Audit live integration acceptance

Baseline: current `origin/main` fetched on 2026-09-14, `ed5925c5`.
Branch and Draft PR: `backend/audit-live-acceptance`.

## Scope and fix

Verified upload -> completed Parser -> Scholar adapter/worker -> Audit v2
statuses and field differences -> disk persistence -> retrieval. Only production
change: startup now creates missing parents of UPLOAD_DIR. Before the fix, a fresh
`new-parent/uploads` configuration raised FileNotFoundError during FastAPI startup;
after it, startup and upload succeed. No search provider or matching algorithm added.

## Results

- **Live run:** BibTeX completed parsing; one query returned SCHOLAR_TIMEOUT
  (30.25 seconds for upload/audit). PDF completed parsing and extracted two entries;
  both queries returned SCHOLAR_TIMEOUT (61.55 seconds total). All reports persisted
  and were retrieved unchanged through a new uvicorn process. This confirms bounded
  failure handling, **not successful live publication retrieval**. External availability
  remains an explicit acceptance gap; no retries, bypasses or alternative provider added.
- 71 relevant backend/Engine tests passed (three dependency deprecation warnings).
- Ruff passes for changed Python files; `git diff --check` passes.
- Controlled acceptance uses real FastAPI lifespan/routes, real BibTeX and PDF
  Parser, real Scholar subprocess/adapter and Engine comparison. Only Scholar's
  network iterator is replaced inside a test worker. This is NOT live search success.
- BibTeX: VERIFIED, METADATA_MISMATCH, NOT_FOUND, timeout LOOKUP_FAILED,
  worker-failure LOOKUP_FAILED, rate-limit LOOKUP_FAILED. Year comparison records
  input 2020 vs source 2017 as MISMATCH. Mixed failures preserve successful entries.
- PDF: Parser completes and extracts two references. Results are NEEDS_REVIEW
  (different author formatting, conservatively retained) and METADATA_MISMATCH.
- Invalid PDF returns 415; missing or conflicting Audit inputs return 422.
- Both reports match their JSON files and GET responses, including retrieval over
  HTTP from a **new uvicorn process**, launched from the documented backend directory.
- See `controlled/controlled-evidence.json` and `live/live-evidence.json` for actual
  requests, parse responses, reports, durations and restart checks. Per-input response
  files also preserve reports before subsequent acceptance assertions.

## Reproduction

Install the repository backend, Parser and Engine dependencies and Java required
by OpenDataLoader. From `claimtrace/`, with the project's Python environment:

```sh
python backend/scripts/audit_live_acceptance.py --mode controlled --output docs/audit-live-acceptance/controlled
python backend/scripts/audit_live_acceptance.py --mode live --output docs/audit-live-acceptance/live
python -m pytest backend/tests/test_audit_startup.py backend/tests/test_bibliography_audit.py backend/tests/test_bounded_scholar_lookup.py backend/tests/test_bib_api.py engine/tests/test_google_scholar_lookup.py engine/tests/test_scholar_search.py -q
```

The runner ignores developer .env, disables LLM credentials, selects this checkout's
Engine/Parser, and isolates all uploads in a temporary directory. No existing user
uploads are touched. Uvicorn is terminated on completion. Report IDs in committed
evidence belong to the removed temporary database; rerun to generate new IDs.

Live mode uses the existing Google Scholar worker, 30-second deadline per query,
and 2-second spacing. Controlled timeout shortens the subprocess deadline to 0.2
seconds and actually terminates a sleeping child; the production adapter retains
its configured 30-second message. Worker failure exits nonzero, and rate limiting
raises the library's DOSException. None of these fixtures is a production provider.

## Contract and limitations

- Upload via multipart `POST /api/parse`, field `file`; confirm `status=completed`
  (also checked through `GET /api/parse/{paper_id}`).
- Audit accepts exactly one of `bib_paper_id` / `manuscript_id`.
- POST `/api/audit` returns the completed report synchronously. GET
  `/api/audit/{audit_id}` reads persisted history, not background job progress.
- `contract_version=2`; reports include counts, results, warnings and status.
  Each result includes entry, field_checks, matched_record/candidates and lookup_attempts.
- NOT_FOUND requires a completed negative search; timeouts, worker failures and
  rate limits stay LOOKUP_FAILED. Audit does not judge claim entailment and needs
  no source PDF uploads for a BibTeX input.
- PDF fixtures are synthetic, visually checked, with abbreviated author metadata
  and an intentionally duplicated title with a wrong year. They are not complete
  scholarly citations or a measurement of real lookup recall.
- Current Parser rejects a reference section with only one entry (requires two).
  The initial single-entry sample returned needs_review with zero results and a
  warning. This existing Parser boundary is documented, not changed in this PR.
- Scholar currently narrows queries to the supplied year. A wrong-year citation
  may produce no match rather than field differences in live search. Controlled
  differences prove downstream handling only; provider matching remains unchanged.
- No frontend/browser acceptance or changes are included. Draft status must remain
  until the team accepts the live-search evidence and any external availability limits.
