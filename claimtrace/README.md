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

| Role | Member | Team |
|------|--------|------|
| Tech Lead / Engine Architecture | — | Engine Team |
| PDF Parser & Element Extraction | — | Engine Team |
| Embedding & Retrieval | — | Engine Team |
| Entailment Verification | — | Engine Team |
| Backend API | — | Backend Team |
| Backend Pipeline & DevOps | — | Backend Team |
| Frontend + Chrome Extension | — | Frontend (Solo) |

```
┌─────────────────────────────────────────────────────────────┐
│                    Tech Lead (Engine)                       │
│                                                             │
│  统筹 Engine 流水线 (parser → retriever → verifier)          │
│  跨队接口对齐 · Benchmark 维护 · 架构决策                     │
└──────────────────┬──────────────────────────────────────────┘
                   │
    ┌──────────────┼──────────────┐
    │              │              │
    ▼              ▼              ▼
┌────────┐  ┌──────────┐  ┌──────────┐
│Engine  │  │ Backend  │  │ Frontend │
│Team    │  │ Team     │  │ (Solo)   │
│(4人)   │  │ (2人)    │  │ (1人)    │
└───┬────┘  └────┬─────┘  └────┬─────┘
    │            │             │
    │  Python    │  FastAPI    │  React + Chrome Ext
    │  module    │  service    │  REST consumer
    └────────────┼─────────────┘
                 │
        Python import       REST API boundary
```

---

## Project Structure

```
claimtrace/
├── parser/          # PDF → clean structured text
│   ├── src/
│   │   ├── pdf_parser.py          # Text extraction, 2-col reorder, paragraphs
│   │   ├── element_extractor.py   # Formula, table, figure detection
│   │   └── reference_extractor.py # Bibliography parsing
│   └── tests/
│
├── engine/          # claim → matched source passage + verdict
│   ├── src/
│   │   ├── embedder.py            # sentence-transformers wrapper
│   │   ├── retriever.py           # FAISS index + two-stage retrieval
│   │   └── verifier.py            # LLM entailment: SUPPORT/PARTIAL/CONTRADICT/NOT_FOUND
│   └── tests/
│
├── backend/         # FastAPI orchestration layer
│   └── src/
│       ├── main.py                # App entry, CORS, router mounting
│       ├── models.py              # Shared Pydantic models (API contract)
│       └── routes/
│           ├── parse.py           # POST /api/parse, GET /api/parse/{id}
│           ├── verify.py          # POST /api/verify
│           └── audit.py           # POST /api/audit
│
├── frontend/        # Web Audit Dashboard (React + Vite + TypeScript)
│   └── src/pages/
│       ├── UploadPage.tsx         # Multi-PDF upload + parse status
│       ├── VerifyPage.tsx         # Single claim verification
│       └── AuditPage.tsx          # Batch audit report
│
├── extension/       # Overleaf Chrome Extension (Manifest V3)
│   └── src/
│       ├── content.js             # DOM injection + hover detection
│       └── popup.html             # Extension popup
│
└── docs/
    ├── team-charter.md
    ├── architecture.md
    ├── spike-reports/
    └── user-research/
```

---

## Quick Start

```bash
# Prerequisites: Python 3.11+, Node.js 20+, Docker

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

### Branch Strategy

```
main ─────────────────────────────────────────────
  │
  ├── engine/parser-core        ← Engine Team
  ├── engine/retrieval          ← Engine Team
  ├── engine/verification       ← Engine Team
  ├── backend/api               ← Backend Team
  ├── frontend/ui               ← Frontend Solo
  └── frontend/extension        ← Frontend Solo
```

- Feature branches live ≤ 1 week. Merge to `main` every Friday.
- `main` is always deployable (at minimum, it doesn't crash).

### Daily Routine

```bash
# 1. Start of every day — rebase on latest main
git checkout main && git pull origin main
git checkout your-branch && git rebase main

# 2. Commit with module prefix
git add <only your files>
git commit -m "parser: fix hyphenation repair regex"
git commit -m "engine: add sentence-level re-ranking"
git commit -m "backend: wire /verify to engine.verifier"
git commit -m "frontend: add upload progress bar"

# 3. Push + open PR
git push origin your-branch
# PR → CI must pass → ≥1 approve → Squash merge
```

### Conflict Prevention

| Rule | Detail |
|------|--------|
| **文件归队所有** | 不跨队改不属于自己目录的代码 |
| **models.py 走流程** | 修改 API 契约需 Tech Lead + Backend lead 都 approve |
| **改共享文件先喊** | `docker-compose.yml`、`.gitignore`、CI config — 改之前在 Discord 说一声 |
| **同队改同文件先对齐** | 花 5 分钟口头约定：你改前面，我改后面，你先合 |
| **每天 rebase，不要攒** | 三周没 rebase → 50 个 commit 冲突 = 灾难 |

### PR Rules

1. CI must pass (lint + tests for all four modules)
2. At least 1 approval required
3. Squash merge to `main` (keep history linear and clean)
4. If you're unsure → open a **Draft PR** first, ask for early feedback

### Git Configuration (everyone, once)

```bash
git config --global pull.rebase true        # git pull = rebase, not merge
git config --global rebase.autoStash true   # auto-stash before rebase
```

---

## Sprint Cadence

```
W1-W3: 准备期 (Spike + 用户研究 + Pitch)
W4-W9: Sprint 执行 (3 × 2-week Sprints)
W10-W11: 收尾 (测试 + 打磨 + Demo 视频)
W12: Demo Day

Engine Team Sprint Plan:
  Sprint 1 (W4-W5): Baseline Pipeline — PDF → claim → verdict 全链路跑通
  Sprint 2 (W6-W7): Quality Push — Recall@5 ≥ 0.80, Entailment Acc ≥ 0.85
  Sprint 3 (W8-W9): Integration + Edge Cases — 接入 Backend, 处理真实场景

Backend Team Sprint Plan:
  Sprint 1 (W4-W5): Parse + Verify endpoints, Mock data for Frontend
  Sprint 2 (W6-W7): Audit batch endpoint, error handling, rate limiting
  Sprint 3 (W8-W9): Performance, caching, production hardening

Frontend Sprint Plan:
  Sprint 1 (W4-W5): Upload + Verify pages (against Mock API)
  Sprint 2 (W6-W7): Audit dashboard + batch result rendering
  Sprint 3 (W8-W9): Chrome Extension (hover → popup → verdict)
  Sprint 4 (W10): Polish + Demo video recording
```

---

## Weekly Meeting Rhythm

| Day | Meeting | Who | Duration |
|-----|---------|-----|----------|
| Monday | Standup | All 7 | 15 min |
| Wednesday | Engine Team deep sync | Engine Team | 30 min |
| Thursday | Cross-team alignment | Tech Lead + Backend lead + Frontend | 20 min |
| Friday | Sprint Review + Retro + Planning | All 7 | 75 min |
| Friday | Workshop | All 7 | 3 hours |

---

## Key Dates

| Date | Milestone |
|------|-----------|
| 20 Aug 2026 | A1: Project Pitch Slides Due |
| 21 Aug 2026 | A1: In-Class Presentation |
| 22 Oct 2026 | A4: Demo Video + Slides Due |
| 23 Oct 2026 | A4: In-Class Demo |

---

## API Contracts

Engine → Backend is a direct Python import (not REST). No API overhead inside the monorepo.

Backend → Frontend/Extension is REST:

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/health` | GET | Service health check |
| `/api/parse` | POST | Upload & parse a PDF |
| `/api/parse/{id}` | GET | Get parse status |
| `/api/verify` | POST | Verify a single claim against source |
| `/api/audit` | POST | Batch audit all citations in a manuscript |
| `/api/audit/{id}` | GET | Get audit results |

Full schema: `backend/src/models.py` | Interactive docs: `http://localhost:8000/docs`

---

## Technology Stack

| Layer | Tech | Owner |
|-------|------|-------|
| PDF Parsing | PyMuPDF, pdfplumber | Engine |
| Formula OCR | Nougat / Pix2Text (W3) | Engine |
| Embeddings | sentence-transformers (all-MiniLM-L6-v2) | Engine |
| Vector Index | FAISS | Engine |
| LLM Verification | GPT-4o / Gemini 2.0 Flash | Engine |
| Backend | FastAPI + Uvicorn | Backend |
| Frontend | React 18 + Vite + TypeScript | Frontend |
| Extension | Chrome Manifest V3 | Frontend |
| CI/CD | GitHub Actions | Backend |

---

## License

MIT
