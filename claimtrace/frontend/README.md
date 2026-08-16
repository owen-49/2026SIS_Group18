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
- `/library` — linked paper library
- `/upload` — PDF and BibTeX uploads
- `/verify` — single-claim evidence trace
- `/audit` — batch citation audit
