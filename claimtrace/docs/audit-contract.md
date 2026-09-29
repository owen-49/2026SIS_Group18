# Bibliography Audit — contract and limits

Owner: Backend (Audit). Consumers: Backend, Frontend, Extension.

Bibliography Audit checks whether a reference exists in an external publication
record and compares its metadata. It is not claim verification: Audit never ranks
source passages and never classifies claim support. `docs/citation-comparison.zh-CN.md`
covers that other flow.

This file is the whole current contract. It replaces three documents that each held
part of it (`backend-audit-handoff.md`, `audit-live-acceptance/audit-integration-handoff.md`,
and §8 of the former Scholar-replacement proposal).

---

## 1. Product boundary

Verify asks whether one claim is supported by a cited source. Audit asks whether the
cited reference exists externally and whether its metadata agrees. Audit needs no
uploaded source PDF and returns no support rates, contradiction verdicts, similarity
scores or evidence passages. Keep the existing Audit display layout; populate it with
bibliographic records and field differences.

## 2. API

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

Each result carries `entry` (original metadata, raw text, available page positions),
`status`, `reason`, `field_checks`, `matched_record`, `candidates` and
`lookup_attempts`. Field checks expose `field_name`, `input_value`, `source_value`,
`status` and `detail`. An external record carries `provider`, `record_id`, `url`,
`retrieved_at` and metadata.

| Result state | Meaning |
| --- | --- |
| `VERIFIED` | A record was identified and title, authors, year and venue agree. DOI is optional. |
| `METADATA_MISMATCH` | An identified record differs in a field the **reference itself states**. Show both values. |
| `NEEDS_REVIEW` | Ambiguous candidates, incomplete metadata, or agreement only on a value recovered from the raw text. |
| `NOT_FOUND` | Every configured lookup path completed with no eligible record. Does not mean fabricated. |
| `LOOKUP_FAILED` | Provider failures, exhausted attempts, or invalid adapter output. Existence remains unchecked. |

Per-reference failures do not discard successful results. `completed` means processing
finished, not that every entry verified. Empty extraction returns `needs_review`; a run
with lookup failures returns `completed_with_errors`. Input failures use 404/409/422;
missing Parser or runtime dependencies use 503; storage failures use 500, each with
`detail: {code, message}`. FastAPI request validation keeps its standard 422 list.

### The rule the rest of the repository quotes

> A failed query must not be converted to `NOT_FOUND`.

`NOT_FOUND` requires a completed negative search. Timeouts, HTTP failures, transport
failures and rate limits all remain `LOOKUP_FAILED`. This is the reason the five states
exist as five rather than four.

### Reference artifact lifecycle

PDF Audit first reads `PARSED_DIR/{paper_id}.references.json`; a missing artifact is
extracted once and saved atomically, including warnings and available locations.
Invalid, mismatched or stale artifacts return `REFERENCE_ARTIFACT_ERROR` without silent
re-extraction. Explicit PDF reprocessing invalidates old references.

## 3. Lookup: the provider chain

Startup installs `ProviderChainLookup(default_providers())` into
`app.state.bibliography_lookup` (`backend/src/main.py`). The chain is **OpenAlex first,
then Crossref**, both keyless REST APIs queried once each:

- `engine/engine/openalex_lookup.py`
- `engine/engine/crossref_lookup.py`
- assembled by `backend/src/services/provider_chain_lookup.py`

OpenAlex is primary because it indexes the preprints that reference lists cite
alongside the published form, and because it resolves records whose venue survives only
in `raw_source_name`. The chain short-circuits at the first provider that settles a
reference, so a reference OpenAlex resolves never reaches Crossref — measured at one
request and about 1.5 s per resolvable reference.

`EXTERNAL_LOOKUP_NOT_CONFIGURED` survives only as the `lookup is None` fallback and its
test. It is not the normal state.

`DEFAULT_CANDIDATE_LIMIT` is 10 because a correct record was measured at rank 9.

### Identity is decided structurally, not by a weighted score

`engine/engine/identity.py::select_identity` runs a sequence of hard tiers (normalised
DOI, arXiv id, exact title, then title-and-year-and-venue agreement) that either settle
the identity or refuse to. A record that fails a tier is **rejected and the rejection is
reported**, rather than down-weighted and possibly still selected.

A scoring threshold was proposed and deliberately not built: it conflates "is this the
same work?" with "how confident are we?", and cannot be tuned honestly without a
labelled set. Two measured rules fall out of the tier design:

- **A candidate with no venue is rejected.** This is the anti-fabrication rule. It costs
  real coverage — see §7.
- **`abs(reference_year - candidate_year) > 1` rejects.** The tolerance is 1 because 0
  rejects correct IEEE-style references. It is measured, not chosen.

Both are measured rules; relaxing either is a separate change needing its own measurement.

Google Scholar scraping was **replaced, not repaired**: a 30-second timeout was hiding a
blocked scrape rather than a slow one (403/captcha branches in `scholarly` never advanced
its retry counter). Removed: `google_scholar_lookup.py`, `bounded_scholar_lookup.py`,
`scholar_worker.py`, `engine/engine/scholar_search.py`, and the `scholarly` and
`bibtexparser` dependencies. There is no Scholar fallback, no worker subprocess and no
minimum interval between lookups — the providers are documented REST APIs, and a throttle
would have nothing to protect against. `SCHOLAR_*` environment variables are gone; the
only bound is `METADATA_LOOKUP_TIMEOUT_SECONDS` (per socket operation).

## 4. What the comparison reads

This is the part most likely to surprise a reader, and it is deliberate.

**A reference carries two descriptions of itself:** the structured fields a parser
filled in, and its raw text. Which one is complete depends on how the paper was loaded.
The searchability guard, the lookup and the field comparison therefore all read the same
one, through `reference_query_for` — so the audit cannot search on one description and
compare against another.

**For a PDF reference, the raw text is the one that has content.** Measured over the 174
PDF references under `backend/uploads/parsed`: the structured title is non-empty for
exactly one, and the raw text yields one for 173. The structured path exists — the Parser
emits `Reference` with title/authors/year/venue/doi — it is just empirically near-empty
on this corpus.

**Query text comes from the reference, not only from its structured fields.** A BibTeX
block is never re-parsed as a reference-list entry: doing so recovers a corrupted DOI that
would silently disable the identifier tier.

**A difference recovered from the raw text withholds `VERIFIED`; it does not accuse.** A
difference in such a value may be the extraction's rather than the reference's, so it
returns `NEEDS_REVIEW` and never `METADATA_MISMATCH`. A difference in a value the
reference's *own metadata* states is still `METADATA_MISMATCH`: that value is the user's.

This distinction is load-bearing. A plain swap of the compared field source — the obvious
fix, without this rule — turns two thirds of the corpus into accusations, because the
reference abbreviates venues the record spells out (`ACL` against the full proceedings
name). Reporting those as `METADATA_MISMATCH` told the user their reference was wrong.

### The author gate

`VERIFIED` compares each author's **surname** and the given names **both sides state**.
Name order, middle initials and accents are how a source spells a name, not what it says.
It still refuses a stated difference: "Smith, Jane" against "Smith, John" shares a surname
and is not the same person. A name one side abbreviates cannot contradict, so
`"Vaswani, A."` is never refused against `"Vaswani, Ashish"`.

The surname rule is `engine.bib_parser.author_surnames` — the one place this project
decides what a surname is, reused rather than redefined.

This gate is stricter than the Engine's on purpose. Over-refusing a true match costs a
`NEEDS_REVIEW`. The residue is dominated by references listing fewer authors than the
record (an `et al.` or a truncated extraction).

## 5. Measured behaviour

Reproduce over your own recorded audits:

```sh
python backend/scripts/audit_comparison_measurement.py DIR
```

`DIR` holds the `*.json` audits the route persisted, by default
`backend/uploads/parsed/audits/`. `uploads/` is gitignored, so this is a reviewer-runnable
tool, not a CI test — the same standing as `audit_live_acceptance.py`, which needs network.

The script re-runs the recorded results three ways over the same entry and record:
`recorded` (what the audit wrote at the time), `naive` (the field-source swap without the
recovered-value rule) and `current`. It self-checks that the pre-change path reproduces
the recorded statuses, and fails loudly if not.

**Counts are corpus-relative and drift as audits accumulate.** Quote them with the corpus
size and date, or quote the command. Measured over the 91 matched records present on
2026-09-19: `0 VERIFIED / 0 METADATA_MISMATCH / 91 NEEDS_REVIEW` before the comparison
change, `18 / 0 / 73` after, `10 / 62 / 19` for the naive swap. Author agreement: 69 of 91
under the current gate, 36 under the element-wise comparison it replaced. The 22 that do
not agree divide into 10 references listing fewer authors, 2 listing more, and 10
disagreeing at equal length.

## 6. Acceptance evidence

Committed under `docs/audit-live-acceptance/`, with fixtures (`manuscript.pdf`,
`references.bib`) as **inputs**: `--output DIR` requires a directory already containing
them.

```sh
cd claimtrace
# write to a scratch directory unless you mean to replace the committed evidence
python backend/scripts/audit_live_acceptance.py --mode controlled --output /tmp/acceptance/controlled
python backend/scripts/audit_live_acceptance.py --mode live --output /tmp/acceptance/live
```

The runner ignores developer `.env`, disables LLM credentials, selects this checkout's
Engine and Parser, and isolates all uploads in a temporary directory. No existing user
uploads are touched. Uvicorn is terminated on completion. Report IDs in the committed
evidence belong to a removed temporary database; rerun to generate new IDs.

**Controlled mode** replaces the bytes each provider's HTTP request receives, via
`controlled_http_get_json`. It patches `engine.openalex_lookup.http_get_json` and
`engine.crossref_lookup.http_get_json` — the names imported into each provider's
namespace — because patching `engine.metadata_lookup.http_get_json` instead would leave
both providers on the real network and the run would silently stop being controlled.
Everything else is production code: the real FastAPI lifespan and routes, the real BibTeX
and PDF Parser, the real response mappers, the real identity rules, the real adapter and
the real Engine comparison.

Its five fixtures are: a 200 with a matching record (`found`), a 200 with an empty result
list (absent), a 429 (throttled), a 500 (provider failure), and `status_code=0`
(transport failure). None is a production provider, and **passing controlled mode is not
evidence that live retrieval works**.

**Live mode** issues the real HTTP requests: one per provider per reference, no retries,
no spacing between references, bounded only by `METADATA_LOOKUP_TIMEOUT_SECONDS` (per
socket operation). It needs outbound network access and reports `LOOKUP_FAILED` when
there is none — a failure to check, never a claim of absence.

### Reading the committed snapshots

`controlled/` and `live/` hold snapshots recorded **2026-09-21** against the current
provider chain: every lookup attempt names `openalex` or `crossref`, and no record carries
`google_scholar`.

The Scholar-era snapshots recorded 2026-09-14 — 30 `provider="google_scholar"` entries and
`SCHOLAR_TIMEOUT` — are preserved unedited under `archive-scholar-era/`. They record what
actually happened at the time and were moved rather than overwritten, because editing a
record to match later behaviour falsifies it.

**Read the live snapshot's headline result before treating it as a regression.** Its single
BibTeX entry is "Attention Is All You Need", and it reports `NOT_FOUND` — see §7, where that
is the documented limitation rather than a failure of the chain. The Scholar-era run over
the same fixture reported `LOOKUP_FAILED`, so the change from `LOOKUP_FAILED` to `NOT_FOUND`
is the lookup completing, not the answer improving.

A snapshot records **when it was taken**, not current behaviour. Nothing fails when it
goes stale, because the script's assertions check live output rather than the snapshot.

## 7. Known limits

- **Coverage is lost before the rules run, and then to the rules.** A reference whose
  candidates are other papers reports `NOT_FOUND` where Scholar would have returned a hit.
  This is the anti-fabrication behaviour working at both layers, and it is a real cost
  rather than a bug. Do not relax the venue requirement or `NON_PUBLICATION_KINDS` without a
  measurement showing what the relaxation admits.

  The clearest example is the most-cited paper in the field. Measured 2026-09-21,
  `filter=title.search:Attention Is All You Need&per-page=10` returns ten records and **none
  is the Vaswani et al. paper**: nine share the title but not the year and are rejected as
  ineligible, and the tenth is a venue-less 2025 preprint carrying the real paper's 7,608
  citations — a hijacked title, and the one `openalex_lookup.py` names as the reason
  `locations[]` is never consulted. Adding `publication_year:2017` to the filter returns
  **zero** records, so there is no correct OpenAlex record for the title search to rank.
  The audit reports `NOT_FOUND`, names the rule that fired, and says it does not prove
  fabrication.

  Two consequences are worth keeping straight. The loss is not only the venue rule: a record
  must be **in the returned page** before any rule can accept it, and this title has 266
  matches with a page size of 10. And `NOT_FOUND` here is not a claim that the paper does
  not exist — it is the report declining to verify against records it cannot trust, which is
  the same choice the venue rule makes. `live/` now records this case, so it is reproducible
  rather than asserted.
- **The identity rules decide before any field comparison, and they are strict.** A
  wrong-year citation is rejected as *ineligible* rather than reported as a field
  difference, so there are **no field checks at all** for that entry. The rejection is
  pointed rather than silent: the reason reads, for example, "20 of 20 records were
  ineligible (10 no venue, 10 year disagrees)".
- **The comparison reads raw text because the structured fields are empty.** This is
  measured (1 of 174), not assumed, and it is the reason the recovered-value rule exists.
  Fixing the Parser's structured output would not remove the rule — it would make it
  apply less often.
- **The Parser rejects a reference section with only one entry** (it requires two). The
  initial single-entry acceptance sample returned `needs_review` with zero results and a
  warning. This is a Parser boundary, documented rather than changed.
- **No frontend or browser acceptance is included here.** See
  `docs/audit-live-acceptance/live/overleaf-external-acceptance-2026-09-19.md` for the
  manual end-to-end record over the real plugin and backend.
- **The frontend accepts no manual source-PDF override for Audit.** Candidates remain
  informational.
- **Extraction damage is not detected.** `"Jan Šediv\`y"` against `"Ján Šedivý"` and a
  record whose author is a different person (`"Cordelia Schmid"` against
  `"Calvin F. Schmid"`) both surface as `NEEDS_REVIEW`, not as an error.

## 8. Standalone `/api/verify/bib`

`POST /api/verify/bib` is a separate, older flow: it compares an uploaded BibTeX entry
against an uploaded source PDF's first-page metadata, returning per-field
`MATCH` / `MISMATCH` / `PDF_MISSING` / `BIB_MISSING`. It never contacts an external
provider. Its local PDF comparison is **not** existence proof, and it is deliberately
unchanged by the Audit work.

```json
{
  "bib_paper_id": "<bib paper id>",
  "source_paper_ids": ["<uploaded pdf id>"]
}
```
