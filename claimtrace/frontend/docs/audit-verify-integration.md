# Audit / Verify integration

The web Review claims page discovers citations with `GET /api/papers/{manuscript_id}/claims` and analyzes only the user's selected citation with `POST /api/verify/citation`. Requests preserve the selected text and send the returned `claim_id`, `manuscript_id`, and a single `citation_marker`. A selected bibliography is passed as `bib_paper_id` to both endpoints.

Only `COMPARED` with a valid judgement renders a verdict. All other statuses, including unknown future statuses, retain the backend message, source information and evidence without a verdict. Changing the selection or bibliography clears the previous result; leaving the page cancels pending requests. Existing Audit v2 requests and the page layout are retained.

## Validation

From `claimtrace/frontend`:

```sh
npm ci
npx playwright install chromium
npm run lint
npm run build
npm run test:integration
```

If Google Chrome is already installed, `PLAYWRIGHT_CHANNEL=chrome npm run test:integration` runs against that browser instead. Tests start their own frontend on port 3100 and intercept backend requests; they do not require API keys or call a model.

The 20 browser tests cover all current non-comparison statuses plus an unknown status, all four real verdicts, invalid judgements, exact request fields, optional bibliography, numeric reference groups, network/503 errors, stale responses after navigation, and Audit v2 PDF/BibTeX requests.

## Dependencies and limitations

- Requires the backend contract merged in PR #29; see `claimtrace/docs/verify-reference-integration-handoff.md`.
- Real comparison requires configured backend LLM access and an available parsed source PDF. Browser tests prove frontend behavior with controlled responses, not live model accuracy or full end-to-end readiness.
- The new endpoint has no manual source PDF override. Candidate records remain informational; the UI does not submit a candidate as a confirmed source. Supporting overrides requires a separate API agreement.
- Selection must match a citation returned by the claims endpoint. Numeric groups such as `[7,8]` and `[7-9]` offer one-reference selection; this change does not expand general citation-format support.
- Example mode uses clearly labelled prepared results. Backend, Engine, parser, extension and CI files are unchanged.
