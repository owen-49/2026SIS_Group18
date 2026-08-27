# ClaimTrace Dashboard

React + Vite + TypeScript dashboard for the ClaimTrace citation audit workflow.

## Run locally

```bash
npm install
npm run dev
```

The app opens at `http://localhost:3000` and uses deterministic demo data by default, so the complete interface works without the backend.

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

- `/` — workspace overview
- `/library` — uploaded manuscript library with an in-page upload window
- `/upload` — redirects to the Paper Library upload window for compatibility
- `/verify` — manuscript claim and database citation review
- `/audit` — batch citation audit

In real API mode, `/library` loads persisted records from `GET /api/papers` and displays uploaded PDFs only. Academic-database articles used for citation comparison are shown in review results, never mixed into Paper Library.

The `/verify` screen is analysis-driven: it selects an uploaded manuscript, shows its extracted text on the left, loads claim-and-citation pairs from `GET /api/papers/{paper_id}/claims`, and shows database citation resolution on the right. An identified cited source is automatic; a missing citation may return optional `similar_sources` candidates that the user can choose for comparison without treating the candidate as the original citation. Until the claims endpoint is available, real API mode shows an explicit unavailable or pending state.
