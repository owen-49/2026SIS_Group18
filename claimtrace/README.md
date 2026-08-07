# ClaimTrace

> The Academic Citation Audit Engine

**Tagline**: Don't let Reviewer 2 find your citation mistakes first.

---

## What is ClaimTrace?

ClaimTrace is a browser extension + web dashboard that verifies whether claims
in your academic paper accurately reflect the sources they cite. It answers one
question: *"Does the cited paper actually say what you claim it says?"*

- **Semantic Lineage Engine**: Finds the original passage in a source PDF that
  supports (or contradicts) a claim — even when the wording is completely
  different.
- **Overleaf Hover Audit**: Hover over `\cite{...}` in Overleaf to instantly
  see the matched source text, without leaving your writing flow.
- **Batch Audit Dashboard**: Upload your manuscript + all cited PDFs and get a
  risk-ranked report of which citations need human review.

---

## Team

| Role | Member | Pair |
|------|--------|------|
| PDF Architecture | — | Pair 1: Document Intelligence |
| Element Extraction | — | Pair 1: Document Intelligence |
| Retrieval | — | Pair 2: Semantic Engine |
| Verification | — | Pair 2: Semantic Engine |
| Backend API | — | Pair 3: Application |
| Frontend + Extension | — | Pair 3: Application |
| Product & Quality | — | Solo |

---

## Project Structure

```
claimtrace/
├── parser/          # Pair 1: PDF → clean structured text
├── engine/          # Pair 2: claim → matched source passage
├── backend/         # Pair 3-A: FastAPI orchestration
├── frontend/        # Pair 3-B: Web audit dashboard
├── extension/       # Pair 3-B: Overleaf Chrome Extension
└── docs/            # Team charter, architecture, research
```

---

## Quick Start

```bash
# Prerequisites
# - Python 3.11+
# - Node.js 20+
# - Docker

# Clone and start all services
git clone <repo-url>
cd claimtrace
docker compose up

# Or run individually
cd parser && pip install -e ".[dev]" && pytest
cd engine && pip install -e ".[dev]" && pytest
cd backend && pip install -e ".[dev]" && uvicorn src.main:app --reload
cd frontend && npm install && npm run dev
```

---

## Development Workflow

1. Each Pair works on their own branch: `pair1/*`, `pair2/*`, `pair3/*`
2. PRs require ≥1 approval and passing CI before merging to `main`
3. Pre-commit hooks: `ruff` (Python), `prettier` (JS/TS)
4. Weekly sprint reviews on Fridays

---

## Key Dates

| Date | Milestone |
|------|-----------|
| 20 Aug 2026 | A1: Project Pitch Slides Due |
| 21 Aug 2026 | A1: In-Class Presentation |
| 22 Oct 2026 | A4: Demo Video + Slides Due |
| 23 Oct 2026 | A4: In-Class Demo |

---

## License

MIT
