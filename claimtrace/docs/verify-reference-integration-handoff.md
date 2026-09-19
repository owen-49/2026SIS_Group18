# Verify reference integration — Hongyang handoff

## Delivered scope

This branch connects existing persisted reference metadata to single-claim Verify. It does not change Engine, Parser, web or extension source code. Source PDFs must already be uploaded and parsed; automatic external full-text acquisition remains a product decision.

- `POST /api/verify/citation`: adds optional `bib_paper_id`.
- `GET /api/papers/{manuscript_id}/claims`: adds optional `bib_paper_id` query parameter and additive `claims[].resolution_message`.
- Both routes use the same source locator. Claims discovery does not run the LLM.
- `/claims` builds one request-scoped lookup context (paper records, reference input,
  and source-PDF catalog) and reuses it for every marker. It does not reload or hash
  the same reference artifact once per citation.
- `[7]` resolves by the Parser's stored `number == 7` in that manuscript, never by list position or an unrelated `.bib` key. A missing artifact uses the existing Audit reference extractor/cache; an invalid artifact is not silently replaced.
- `(Smith, 2024)` with a manuscript and no explicit `.bib` uses the manuscript reference metadata. Explicit `.bib` selection takes precedence for author-year/key markers; numeric markers always use the manuscript.
- Key markers with no explicit bibliography retain the legacy single-bibliography fallback. Multiple uploaded bibliographies require an explicit selection.
- A reference can be identified even if its source PDF is unavailable. DOI conflicts and tied/near-tied source matches are not silently accepted. Local association does not prove publication existence.
- `[7,8]` and `[7-9]` return `REFERENCE_AMBIGUOUS`: the client must let the user select one reference, then send the selected single marker with the original selected claim text.
- Missing/wrong-type/not-ready reference inputs return `SOURCE_NOT_AVAILABLE` with the underlying input error code in the message; missing numbers return `REFERENCE_NOT_FOUND`. No new verdict enum is introduced. No failure is converted to a judgement.

## Requests for frontend owners

PDF workflow:

```http
GET /api/papers/MANUSCRIPT_ID/claims
```

```json
{
  "claim": "The method improves retrieval [7].",
  "citation_marker": "[7]",
  "manuscript_id": "MANUSCRIPT_ID",
  "claim_id": "CLAIM_ID_FROM_CLAIMS"
}
```

Send the JSON to `POST /api/verify/citation`. `claim_id` is an echo/correlation token, not an authorization or source-selection token. The claim remains the user's selected text.

BibTeX / extension workflow:

```http
GET /api/papers/MANUSCRIPT_ID/claims?bib_paper_id=BIB_UPLOAD_ID
```

```json
{
  "claim": "The method improves retrieval.",
  "citation_marker": "\\cite{smith2024}",
  "bib_paper_id": "BIB_UPLOAD_ID"
}
```

Only `status == COMPARED` carries `judgement`. Render `message` for other statuses, preserving any returned source/evidence. `resolution_status == identified` in `/claims` means a reference was associated, not that a model judged it or that a PDF exists. Use `cited_source.source_paper_id` to tell whether an uploaded source was found. Missing LLM configuration remains HTTP 503 as in main.

**Update (2026-09-19).** The migration this section asked for is done: the web Review page calls
`/api/verify/citation`, and the extension calls no Verify endpoint at all. The legacy
`/api/verify` now has no client in the repository.

It also no longer hides a failure behind a verdict. When an Engine the endpoint did configure
declines to judge, it answers **503** with
`{"detail": {"code": "<VerificationStatus>", "message": "<Engine rationale>"}}` instead of a
`SUPPORT`/`NOT_FOUND` the Engine never reached. The response *shape* is unchanged, and no
frontend or extension file was touched. The one case that still returns 200 with a
lexical verdict is the announced no-LLM baseline, where no model call was attempted at all.
See `engine-verify-contract.zh-CN.md` §6.2.

## Coordination required / suggested decisions

| Person | Confirm or do | Recommended resolution |
|---|---|---|
| Zheng | `StoredReference.number` corresponds to the visible citation number; metadata fields are compatible with existing Audit output | Review this consumer using one IEEE and one APA sample. Keep the Parser contract unchanged for this PR; provide real sample artifacts. Later richer sentence/marker offsets can be additive. |
| Yi | Uploaded source PDF preserves paragraphs and page locations | Provide one manuscript and cited PDF pair and run real upload/parse, then the requests above. Report empty/mislocated paragraphs to Parser, not Engine. |
| Junli | Explicit bibliography selection, single-reference choice, failure/evidence rendering | Keep chosen bibliography ID in page state, pass it to both endpoints, switch to `/verify/citation`, display `resolution_message` when needed. No layout redesign required. |
| Yiyang | Extension keeps the backend ID returned by its Bib upload and sends it on Verify | Use `bib_paper_id`; do not rely on whichever `.bib` is globally unique. For ambiguous source PDFs, current backend does not yet accept a manual `source_paper_id` override: keep unjudged and agree that optional contract separately. |
| Sichen | New API mapping and Engine evidence contract remain compatible | Review comparison-service call only; no Engine changes here. LLM deadlines and Scholar provider choice stay in separate PRs. |
| Siyuan | Main backend reviewer | Review context isolation, failure handling, shared `/claims` lookup and source matching regressions. Approve after tests and contract review. |
| Hongyang + Sichen | Does this week's acceptance allow manually uploaded cited PDFs? | Recommend accepting manual source upload for this milestone. If automatic full text is mandatory, separately assign download/source acquisition, retry/storage and Parser integration; this branch does not implement it. |

## Acceptance boundary

Automated integration tests use real storage, FastAPI routes and the Engine comparison flow with a fake retriever and fake LLM. They do not demonstrate live model quality, Scholar success, browser rendering or full PDF upload-to-LLM acceptance. No API keys are needed for them.

Before calling the user workflow complete: Yi supplies real PDFs; Hongyang checks upload/parse and source association; Junli/Yiyang call the new endpoint; Sichen provides working model configuration; verify a successful comparison and missing-source/model-failure rendering. API contract review can proceed before this cross-team acceptance.

## Validation performed on 2026-09-15

- Entire backend suite plus `engine/tests/test_verifier.py`: **216 passed**, including 15 new reference integration cases.
- Changed-file Ruff and `git diff --check`: passed.
- Run used Python 3.12 in an isolated environment; `HF_HUB_OFFLINE=1`, with LLM credentials isolated by backend fixtures. No paid model calls or browser acceptance were performed.
- The first focused run completed its assertions but exited during pytest cleanup of a pre-existing Windows temporary-directory link. The complete successful run used a fresh workspace-local `--basetemp`.

Reproduce from the `claimtrace` directory after installing project/test dependencies:

```powershell
$env:PYTHONPATH = "$PWD;$PWD/engine;$PWD/parser"
$env:HF_HUB_OFFLINE = "1"
python -m pytest backend/tests engine/tests/test_verifier.py -q
```

On Windows, if the global pytest temporary directory is inaccessible, add `--basetemp` pointing to a new disposable directory inside your workspace. CI still needs the separate root-workflow fix; these are local results.
