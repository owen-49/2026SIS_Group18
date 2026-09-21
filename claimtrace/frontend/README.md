# ClaimTrace Dashboard

React + Vite + TypeScript dashboard for the ClaimTrace citation audit workflow.

## Run locally

```bash
npm install
npm run dev
```

The app opens at `http://localhost:3000` and talks to the backend at
`VITE_API_URL` (default `http://localhost:8000`). Demo data is **not** the default:
`usingMockApi` is true only when `VITE_USE_MOCK_API` is exactly `"true"`. Setting it to
`true` runs the whole interface offline against deterministic data.

## Connect the API

Copy `.env.example` to `.env.local`, then set:

```env
VITE_USE_MOCK_API=false
VITE_API_URL=http://localhost:8000
```

## Checks

```bash
npm run lint
npm run build
```

## Main routes

- `/` — redirects to `/audit`
- `/library` — redirects to `/audit`
- `/upload` — redirects to `/audit`
- `/audit` — the citation audit workspace (library, upload and results are panels here)
- `/verify` — manuscript claim and source review
- `/extension-setup` — Chrome extension setup instructions
- `/docs` — in-app documentation

Only `/audit` and `/verify` are pages. The library and the upload window are panels
inside the Audit workspace, which is why `/`, `/library` and `/upload` redirect rather
than render. There is no separate Library or Upload page.

In real API mode the Audit workspace loads persisted PDF and BibTeX records from
`GET /api/papers`. It uploads either format through `POST /api/parse` (or
`PUT /api/parse/{paper_id}` to replace a synchronised `.bib`), refreshes pending state
through `GET /api/parse/{paper_id}`, and surfaces backend error messages. Completed
BibTeX records can be checked against completed source PDFs through `POST /api/verify/bib`;
`PDF_MISSING` means the PDF metadata is unavailable, not that the API failed.
External records used for citation comparison appear in review results and are never
mixed into the paper library.

The `/verify` screen selects an uploaded manuscript, shows its extracted text on the left,
loads claim-and-citation pairs from `GET /api/papers/{paper_id}/claims`, and shows
persisted BibTeX / source-PDF resolution on the right. An identified cited source is
automatic; a missing citation may return optional `similar_sources` candidates the user
can choose without treating a candidate as the original citation. Analysis runs through
`POST /api/verify/citation`, and a status other than `COMPARED` renders the backend's
message and evidence **without** a verdict. Real API mode shows an explicit unavailable
or pending state when persisted analysis data is not ready.

The `/audit` screen speaks the bibliography Audit v2 contract: it rejects any response
whose `contract_version` is not 2 and renders all five outcome states. See
[docs/audit-contract.md](../docs/audit-contract.md) for the contract and
[docs/frontend-handoff.md](../docs/frontend-handoff.md) for the frontend's own.
