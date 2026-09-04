# PR #18: bibliography Audit backend correction

## Product boundary

Verify tests whether one claim is supported by a cited source. Audit checks whether
references exist in external publication records and compares their metadata.
Audit needs no uploaded source PDF and does not return support rates, contradiction
verdicts, claim/passage similarity, or semantic evidence passages. Keep the existing
Audit display layout; populate it with bibliographic records and field differences.

## Backend delivered in this correction

- Preserve persisted BibTeX entry responses and real single-Verify claim extraction.
- Replace the semantic batch loop with bibliography input, lookup adapter, existing
  Engine field comparison, five result states, and persisted Audit results.
- Read a selected uploaded Bib from `ParsedBibDocument`; reuse the Parser team's
  `reference_json_extractor.extract_references` for an uploaded manuscript PDF.
- Reuse `engine.bib_verifier.verify_bib_against_pdf` through a backend adapter.
  Its `PdfMetadata` object carries external metadata here; no source PDF is read.
- Preserve both values of each compared field. Existing fuzzy Engine matches are
  conservatively classified as `NEEDS_REVIEW` rather than fully verified.
- Keep local `/verify/bib` unchanged. Its local PDF comparison is not existence proof.
- Keep Verify claims unresolved when numerical references lack a reliable mapping,
  when multiple Bib uploads have no manuscript association, or when keys are ambiguous.

Removed backend paths: semantic `run_audit`, passage ranking, batch LLM verdicts,
risk calculation, semantic Audit response models, and demo Audit output. The former
mixed claims/Audit test now checks claims; bibliography-specific tests cover Audit.
No Parser, Engine, or frontend application code is changed by this correction.

## API v2 (breaking change for the current Audit frontend)

`POST /api/audit` accepts exactly one of:

```json
{"bib_paper_id": "uploaded-bib-id"}
```

```json
{"manuscript_id": "uploaded-manuscript-pdf-id"}
```

Legacy `source_paper_ids` is accepted but ignored, with a response warning.
The response is `BibliographyAuditResponse` in `backend/src/audit_models.py`:
`contract_version: 2`, `audit_id`, `input_paper_id`, `input_type`, `checked_at`,
`status`, `total_entries`, `counts`, `results`, and `warnings`.
`GET /api/audit/{audit_id}` retrieves the persisted result.

Each result contains `entry` (original metadata/raw text and available page positions),
`status`, `reason`, `field_checks`, `matched_record`, `candidates`, and `lookup_attempts`.
Field checks expose `field_name`, `input_value`, `source_value`, `status`, and `detail`.
An external record includes `provider`, `record_id`, `url`, `retrieved_at`, and metadata.

| Result state | Meaning |
| --- | --- |
| `VERIFIED` | Adapter identified an external record and required title/authors/year/venue agree. DOI is optional. |
| `METADATA_MISMATCH` | Identified record has field differences; show the two values. |
| `NEEDS_REVIEW` | Ambiguous candidates, incomplete metadata, or only fuzzy agreement. |
| `NOT_FOUND` | All configured lookup paths completed with no acceptable record. Does not mean fabricated. |
| `LOOKUP_FAILED` | Missing adapter, exhausted request failures, or invalid adapter output. Existence remains unchecked. |

Per-reference failures do not discard successful results. Batch `completed` means
processing finished, not that all entries were verified. Empty extraction returns
`needs_review`; a batch with lookup failures returns `completed_with_errors`.
Input failures use HTTP 404/409/422; missing Parser/runtime dependencies use 503;
storage failures use 500, with `detail: {code, message}`. FastAPI request validation
continues to use its standard 422 error list.

## Existing integration gaps and next ownership decisions

**No external lookup is implemented in the repository.** The dependency
`BibliographyLookup.lookup(ReferenceEntry) -> LookupResult` is an integration boundary,
not a working registry client. Supply an implementation through
`app.state.bibliography_lookup` (or override the route dependency in tests).
Without it every nonempty entry returns `LOOKUP_FAILED` with
`EXTERNAL_LOOKUP_NOT_CONFIGURED`. Tests use an explicit fake lookup and do not prove
live publication existence checks work.

The future lookup implementation needs DOI resolution, bibliographic search when DOI
is absent, raw-reference search where supported, candidate identity decisions,
external evidence URLs/timestamps, bounded timeouts/retries, rate-limit handling,
and caching. A failed query must not be converted to `NOT_FOUND`. Do not automatically
accept the top search hit. No provider, paid subscription, API key, or credential has
been selected or added in this correction; agree ownership and sources before that
implementation. Costs and access requirements remain to be checked for the chosen
provider, rather than assuming an available account or free service.

**Tell the frontend teammate:** keep the Audit page layout and difference display,
but adopt v2 requests/responses, five statuses, metadata field differences and record
links. Remove source PDF prerequisites and semantic labels/data bindings. Handle both
structured backend errors and validation errors. The current PR's frontend types and
Audit page still expect the old semantic contract and are not end-to-end compatible;
update their mocks/tests too. Single Verify continues to use the real claims endpoint.

**Tell the Parser teammate:** the existing reference extractor is wired in and its
raw text, number and pages are preserved. It currently does not return structured
title/authors/year/venue/DOI, so PDF references cannot yet receive complete metadata
verification. Agree a structured reference output with field provenance and missing
values; do not infer bibliographic numbering from Bib order. Existing OpenDataLoader
and Java runtime requirements still apply.

**Tell the Engine teammate:** the current metadata comparator is reused without
editing their package. It performs no external lookup and some author/title matches
are fuzzy. Agree who implements the lookup adapter and candidate disambiguation;
provide external records and query outcomes separately from semantic Verify verdicts.
Prefer an eventual source-neutral metadata comparator interface, without requiring
that refactor for this backend integration.

## Proposed User Story revisions for team agreement

- US-03 remains single-claim semantic Verify.
- US-04 distinguishes local Bib/PDF metadata checking from externally verified Audit.
- US-05: upload/select a manuscript bibliography or Bib, check publication records
  without source PDFs, and display the five outcomes plus field differences.
- US-06: Verify evidence is a source passage; Audit evidence is a retrieved record URL
  and its metadata, with query time/provider.
- US-08/09: review/export bibliography identity and metadata outcomes; do not describe
  Audit as batch entailment or interpret not-found entries as fake references.

These revisions clarify the older Chinese/English User Stories and C4 descriptions.
Those team-owned documents are not wholesale rewritten here. PR #18 is being opened
for formal review at the author's request. Review readiness does not mean the lookup
implementation, PDF field gap, or frontend migration is complete; these remain
explicit scope decisions for reviewers before approving a merge.

## Validation

After integrating main b6504b4, backend tests plus Engine Bib parser/comparator
tests: 131 passed. Ruff passed. Two Verify regression tests cover LLM verdict/
rationale preservation and the no-client lexical baseline; LLM responses are
simulated without paid API calls. Main's Verify implementation is preserved.
The real PDF extractor was also invoked with OpenDataLoader/Java on a generated
one-page reference-list PDF: it ran but returned zero references with the warning
Reference-list heading was not found. This is an unresolved Parser recognition
case, not a successful PDF extraction demonstration. Backend empty-result handling
is covered by tests; no Parser heuristic was changed. No live external lookup was tested.
