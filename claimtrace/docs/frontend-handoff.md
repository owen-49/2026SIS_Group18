# Frontend and Extension — contract and current state

Owner: Frontend (Jun Li, Sam). Consumers: Frontend, Extension.

Covers the React web app in `frontend/` and the Chrome extension in `extension/`. It
replaces `paper-deletion-frontend-handoff.md`, `frontend/docs/audit-verify-integration.md`,
`verify-reference-integration-handoff.md`, and `extension/BACKEND_ALIGNMENT.zh-CN.md`.

---

## 1. The web app

### Routes

From `frontend/src/App.tsx`. Only three routes render a page; the rest redirect.

| Path | Renders |
| --- | --- |
| `/` | redirect → `/audit` |
| `/library` | redirect → `/audit` |
| `/upload` | redirect → `/audit` |
| `/audit` | `AuditPage` |
| `/audit/example` | `AuditPage` in example mode |
| `/verify` | `VerifyPage` |
| `/verify/example` | `VerifyPage` in example mode |
| `/extension-setup` | `ExtensionSetupPage` |
| `/docs` | `DocsPage` |

There is no separate Library or Upload page. Library and upload are panels inside the
Audit workspace, which is why `/library` and `/upload` only redirect.

### API mode

`frontend/src/api/client.ts` reads `VITE_USE_MOCK_API === "true"`; **anything else,
including unset, uses the real backend** at `VITE_API_URL` (default
`http://localhost:8000`). `.env.example` sets it to `false`. Demo data is therefore
available in example mode but is not the default.

### Audit contract

`client.ts` hard-rejects any response whose `contract_version !== 2` or whose `results`
is not an array. `AuditPage` renders all five states. See `docs/audit-contract.md` for
the contract itself.

### Verify / citation comparison

`VerifyPage` discovers citations with `GET /api/papers/{manuscript_id}/claims` and
analyses only the user's selected citation with `POST /api/verify/citation`. Requests
preserve the user's selected text and echo the returned `claim_id`, `manuscript_id` and a
single `citation_marker`. A selected bibliography is passed as `bib_paper_id` to both
endpoints.

**Forward-compatibility rule.** Only `status == COMPARED` with a valid judgement renders a
verdict. Every other status — including a status the frontend does not know — retains the
backend's message, source information and evidence, and shows no verdict. Adding a status
to the backend must not require a frontend release to avoid a false verdict, and this rule
is what makes that true. Keep it.

**Reference resolution.** `resolution_status == identified` in `/claims` means a reference
was *associated*, not that a model judged it or that a PDF exists. Use
`cited_source.source_paper_id` to tell whether an uploaded source was found. `[7,8]` and
`[7-9]` return `REFERENCE_AMBIGUOUS`; the UI must let the user pick one reference and
resend the selected single marker with the original claim text. Missing or unready inputs
return `SOURCE_NOT_AVAILABLE` with the underlying code in the message; a missing number
returns `REFERENCE_NOT_FOUND`. No failure is converted into a judgement.

**LLM unavailability.** A missing LLM configuration is HTTP 503 with
`{"detail": {"code": "<VerificationStatus>", "message": "<Engine rationale>"}}` — the
response shape is unchanged. The one case that still returns 200 with a lexical verdict is
the announced no-LLM baseline, where no model call was attempted at all. See
`docs/engine-contract.zh-CN.md` §6.2.

Changing the selection or the bibliography clears the previous result; leaving the page
cancels pending requests.

### Validation

From `claimtrace/frontend`:

```sh
npm ci
npx playwright install chromium
npm run lint
npm run build
npm run test:integration
```

If Google Chrome is installed, `PLAYWRIGHT_CHANNEL=chrome npm run test:integration` runs
against it instead. The suite starts its own frontend on port 3100 and intercepts backend
requests; it needs no API keys and calls no model.

`frontend/tests/verify-citation.spec.mjs` covers every non-comparison status plus an
unknown status, all four real verdicts, invalid judgements, exact request fields, optional
bibliography, numeric reference groups, network and 503 errors, stale responses after
navigation, and Audit v2 PDF/BibTeX requests. It proves frontend behaviour against
controlled responses, **not** live model accuracy or end-to-end readiness.

---

## 2. Paper deletion

`DELETE /api/papers/{paper_id}` where `paper_id` comes from `GET /api/papers`.

| Response | Meaning | UI |
| --- | --- | --- |
| `204 No Content` | Fully deleted, empty body. | Remove the item. |
| `202 {"paper_id":…,"status":"cleanup_pending"}` | The Library record is **already gone**; purging one or more staged local artifacts failed. A recovery record is retained and cleanup retried on restart or on a repeat request. | **Remove the item**, optionally noting cleanup is pending. |
| `404 {"detail":"Paper not found."}` | Unknown or already deleted. | Keep the view, show the error. |
| `500 {"detail":"Unable to delete the paper and its local artifacts."}` | Failed before the record was removed. | Keep the item, show the error. |

Required behaviour: show delete for both PDF and BibTeX items; confirm before calling,
because deletion is permanent; remove on 204 **and on 202**; keep the item and show an
error on 404/500; block repeat clicks while a request is in flight.

What the backend removes for the selected record: its local upload, Library metadata and
generated files such as parsed JSON. For PDFs it also removes related Markdown, extracted
images, reference data and audit results, when present. Other Library items' files are
never touched.

### Open defect — `deletePaper` rejects the 202

`frontend/src/api/client.ts:88-99`:

```ts
const response = await fetch(apiUrl(`/api/papers/…`), { method: "DELETE" });
if (response.status !== 204) {
  if (!response.ok) await readResponse<unknown>(response);
  throw new Error("Unable to confirm paper deletion.");
}
```

Only 204 is accepted. A 202 satisfies `response.ok`, so `readResponse` is skipped and the
function throws instead — **the user is told deletion could not be confirmed while the
record has in fact been deleted**, and the item stays in the Library view until reload.
This is required behaviour #4 above, not implemented.

Not fixed by the documentation consolidation that produced this file: it is a frontend
source change, and this pass deliberately makes none. Reported here so it is not lost.

---

## 3. The Chrome extension

The extension reads `.tex` and `.bib` content from Overleaf. PDF upload remains a web
workspace feature. Source of truth for the message protocol is
`extension/src/content.js` and the tests in `extension/*.test.cjs`.

### Audit flow

Both the automatic and manual Bib paths call **only** `POST /api/audit`; the extension
calls no Verify endpoint at all. It keeps Audit results, candidate web links, structured
error rendering, and handles a cached ID becoming invalid after the Bib record is deleted
in the backend. PDF Audit sends the selected ID and lets the backend validate it, without
depending on `/api/papers`.

### Synchronised bibliographies

For a previously synchronised `.bib`, the extension stores a SHA-256 of the source text.
An unchanged source reuses the existing paper ID without re-uploading. A changed source
uses `PUT /api/parse/{paper_id}` to replace the content while keeping the same Library
record. `POST /api/parse` is unchanged and is used when no synchronised record exists.

### Links

`US-0x` IDs cited in `content.js` and `hover-card.test.cjs` refer to
`docs/user-research/user-stories.md`. `content.js:273` cites `extension/README.md`, which
is the extension's own contract document.

The extension supports local Bib-entry filtering, jumping to the original URL/DOI, and
opening Audit's `matched_record.url` / `candidates[].url`. With no link it opens a Google
Scholar search for the title — **that is a search shortcut, not a claim that the
reference was found or verified**. There is no standalone paper-search API in this
repository; if one is added, the extension needs its path, parameters, sample response
and branch before it can align.

### Errors and fallback

- Network failures and non-2xx responses show in the Side Panel's backend status and do
  not break Overleaf annotations.
- A citation with no title-matched uploaded PDF stays a clearly labelled local preview
  (`preview: true`).
- Backend-verified findings are stored with `preview: false`.
- Each finding keeps its unique citation-location `id`, so two occurrences of the same key
  get independent results. Stale claim-sync results are ignored, and only `completed` PDFs
  are matched.
- An automatic Bib upload/parse failure writes to a separate `claimtraceBibSyncError` and
  shows that specific error; retrying clears it. A Bib parse error never overwrites a PDF
  Audit's running/completed status.
- Live-paper-list failure and cache-fallback warnings are stored and rendered together;
  they survive the first open, view switches and refreshes, and clear once the list
  reloads successfully.

### Known limits

- **A real logged-in Overleaf + external-service acceptance was exercised manually and
  passed on 2026-09-19** — recorded in
  `docs/audit-live-acceptance/live/overleaf-external-acceptance-2026-09-19.md`. What that
  record does not contain is captured request IDs or raw provider responses. Node DOM
  tests still cannot prove browser layout or long-request stability in the extension
  service worker.
- The backend default is `localhost:8000`; the web workspace is `localhost:3000`.
- **Bibliography state is global**, so multiple Overleaf projects are not isolated. Not in
  scope for any change so far.
- Login-state Overleaf behaviour is untested.

### Validation

```sh
cd claimtrace
node --test extension/*.test.cjs
```

Plus a JS syntax check on each extension file, a manifest resource-existence check, and
`git diff --check`.

---

## 4. `GET /api/papers` returning 500 — root cause, resolved

Reported when the extension loaded the PDF list. Two causes, both fixed:

1. The default `uploads` was resolved relative to the process working directory, so
   starting the backend from the repository root could read an unrelated
   `uploads/papers.json`. It is now pinned to the backend package directory. **Restart the
   backend after changing this.**
2. One corrupt record aborted the whole list. Reading now skips an individual bad record
   and logs it.

**A wholly invalid store still returns 500, deliberately.** If the JSON is not a valid
store at all, silently returning an empty list would look like "you have no papers" and
invite the user to re-upload over data that is merely unreadable. A 500 is the honest
answer. Do not "fix" this into an empty 200.
