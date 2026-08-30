# Backend, Parser, and Chrome Extension Integration Handoff

## Scope

This branch integrates the real PDF Parser with the backend and connects the
Chrome extension to the existing backend APIs. The extension reads `.tex` and
`.bib` content from Overleaf; PDF uploads remain a web audit-workspace feature.

Branch: `backend/real-parser-extension-integration`

## Primary reviewers

- **Yi Jiang and Zheng Fu** — confirm the final Parser output contract and
  improve or replace metadata extraction where the Parser can provide
  structured values.
- **Yiyang Yuan** — load the extension in Chrome and verify the Overleaf,
  Side Panel, and backend flow end to end.
- **Siyuan Sun** — confirm that the existing Bib routes, storage, response
  models, and API contract remain compatible with the integration.
- **Junli Li** — review only if the web frontend consumes the new PDF metadata;
  this branch does not change the React web UI.

## Backend API contract used by the extension

### Upload and parse

`POST /api/parse` with multipart form field `file`.

- The extension sends the detected BibTeX source as `overleaf-references.bib`.
- The backend accepts `.bib` and `.pdf`; the extension only sends `.bib`.
- The response includes `paper_id`, `status`, `file_type`, and parse counts.

### List uploaded papers

`GET /api/papers` returns persisted paper records. The extension uses completed
PDF records to match bibliography titles to uploaded source papers.

### Verify BibTeX metadata

`POST /api/verify/bib` with:

```json
{
  "bib_paper_id": "<bib paper id>",
  "source_paper_ids": ["<uploaded pdf id>"]
}
```

The response contains per-entry field results for title, year, authors, venue,
and DOI, with statuses such as `MATCH`, `MISMATCH`, `PDF_MISSING`, and
`BIB_MISSING`.

### Verify a citation claim

`POST /api/verify` with:

```json
{
  "claim": "<claim text>",
  "source_paper_id": "<uploaded pdf id>"
}
```

The extension maps the response's `verdict`, `confidence`, `rationale`, and
`matches` into the Side Panel finding and editor hover state.

## Extension messages

The content script sends:

```json
{
  "type": "bibliography_detected",
  "papers": ["<locally parsed bibliography entries>"],
  "bibSource": "<raw .bib text>"
}
```

and:

```json
{
  "type": "citations_detected",
  "findings": ["<citation locations and claims>" ]
}
```

The background worker stores backend findings in `chrome.storage.local` and
the content script re-renders them when they arrive.

## Error and fallback behavior

- Network failures and non-2xx backend responses are shown in the Side Panel
  backend status and do not break Overleaf annotations.
- A citation without a title-matched uploaded PDF remains a clearly labelled
  local preview with `preview: true`.
- A citation verified by `/api/verify` is stored with `preview: false` and is
  labelled as backend verified.
- The backend allows valid Chrome extension origins through CORS.

## Parser boundary

`backend/src/services/parser_adapter.py` calls
`parser.pdf_parser.parse_pdf` and maps the result to the stable backend
`ParsedDocument` contract. The contract now includes `authors`, `year`,
`venue`, and `doi` in addition to the parsed paragraphs.

The current Parser on `main` does not populate all structured metadata fields.
The adapter therefore prefers Parser-provided values and uses conservative
first-page text fallbacks for title, authors, year, venue, and DOI. Yi Jiang
and Zheng Fu should confirm the final Parser output before this fallback is
treated as the long-term metadata implementation.

## Validation

- Backend tests: 35 passed.
- Bib Parser/Verifier tests: 67 passed.
- PDF Parser tests: 7 passed, 1 skipped.
- `ruff check backend`: passed.

The full Parser test collection still requires the optional
`opendataloader_pdf` dependency for the Markdown converter tests.

## Explicit non-scope

This branch does not modify Siyuan's Bib backend routes, Bib storage logic,
Bib response models, or the React web frontend. The existing Engine verifier
also remains the repository's deterministic local implementation.
