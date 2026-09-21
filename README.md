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
- **Bibliography Audit**: Upload a manuscript or a `.bib` and have every
  reference checked against real publication records (OpenAlex, then Crossref) —
  no source PDFs required.

---

## Team

Seven people in four groups. See [claimtrace/docs/team.md](claimtrace/docs/team.md)
for ownership, success criteria and process.

| Group | Members | GitHub | Owns |
|-------|---------|--------|------|
| Backend | Hongyang Chen, Siyuan Sun | `chy1145141919810`, `Archieee-coderr` | `claimtrace/backend/` |
| Frontend | Jun Li, Sam | `Li-Jun-Li0577`, `Sam20051512` | `claimtrace/frontend/`, `claimtrace/extension/` |
| Parser | Yi Jiang, Zheng Fu | `johnnyjiangyi01-code`, `Fzddx` | `claimtrace/parser/` |
| Engine | Sichen Liu | `owen-49` | `claimtrace/engine/` |

```
        ┌──────────────────────────────────────────────┐
        │      Four groups, four directories           │
        │  each owns its package end to end            │
        └───────────────────┬──────────────────────────┘
                            │
   ┌──────────┬─────────────┼─────────────┬──────────┐
   ▼          ▼             ▼             ▼          │
┌────────┐┌────────┐  ┌──────────┐  ┌──────────┐    │
│Parser  ││Engine  │  │ Backend  │  │Frontend  │    │
│(2)     ││(1)     │  │ (2)      │  │ (2)      │    │
└───┬────┘└───┬────┘  └────┬─────┘  └────┬─────┘    │
    │         │            │             │          │
    │  Python import (in-process)         │          │
    └─────────┴────────────┘             │          │
                            │  REST /api/*│          │
                            └─────────────┘          │
                                                     │
   Ownership maps to directories, not to layers ─────┘
```

---

## Project Structure

```
claimtrace/
├── parser/          # PDF → structured text + reference list
│   └── parser/                    # the package is flat: parser/parser/
│       ├── pdf_parser.py          # Text extraction, 2-col reorder, paragraphs
│       ├── element_extractor.py   # Text blocks + bounding boxes
│       ├── reference_extractor.py
│       ├── reference_json_extractor.py  # current reference-list extractor
│       └── markdown_converter.py
│
├── engine/          # claim → matched source passage + verdict
│   └── engine/                    # flat too: engine/engine/
│       ├── embedder.py            # sentence-transformers wrapper
│       ├── retriever.py           # FAISS index + two-stage retrieval
│       ├── verifier.py            # LLM entailment
│       ├── bib_verifier.py        # bib × PDF metadata comparison
│       ├── identity.py            # structural record identity
│       ├── openalex_lookup.py / crossref_lookup.py
│       └── llm_client.py          # provider-agnostic
│
├── backend/         # FastAPI orchestration layer
│   └── src/
│       ├── main.py                # App entry, CORS, router mounting, lookup wiring
│       ├── models.py              # Shared Pydantic models (API contract)
│       ├── audit_models.py        # Audit v2 response models
│       ├── routes/                # audit, bib, health, papers, parse, verify
│       └── services/              # parser_adapter, provider_chain_lookup, ...
│
├── frontend/        # Web dashboard (React + Vite + TypeScript)
│   └── src/pages/                 # AuditPage, VerifyPage, ExtensionSetupPage, DocsPage
│
├── extension/       # Overleaf Chrome Extension (Manifest V3)
│   └── src/                       # content.js, background.js, sidepanel.js
│
└── docs/            # current contracts only — see docs/README.md
```

`parser/` and `engine/` are flat: the package is the inner directory, not `src/`.

---

## Quick Start

```bash
# Prerequisites: Python 3.11+, Node.js 20+, Docker, and a Java 11+ runtime
# (OpenDataLoader, used by the PDF Parser, is Java-based; on Java 8 it fails
# with a class-version error — see claimtrace/docs/audit-live-acceptance/).

# Clone and start all services
git clone <repo-url>
cd claimtrace
docker compose up

# Or run individually
cd parser  && pip install -e ".[dev]" && pytest
cd engine  && pip install -e ".[dev]" && pytest
cd backend && pip install -e ".[dev]" && uvicorn src.main:app --reload
cd frontend && npm install && npm run dev
```

The backend serves `http://localhost:8000`; the web app `http://localhost:3000`.
Copy `claimtrace/.env.example` to `.env` for the backend and
`frontend/.env.example` to `frontend/.env.local` for the web app.

---

## Development Workflow

### Branch Strategy

```
main ─────────────────────────────────────────────
  │
  ├── engine/…                  ← Engine group
  ├── backend/…                 ← Backend group
  ├── frontend/…                ← Frontend group
  └── parser/…                  ← Parser group
```

Branch names are `<area>/<what>`, prefixed by the owning directory. Feature branches
live ≤ 1 week and merge to `main` every Friday. `main` is always deployable (at minimum,
it doesn't crash).

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
# PR → CI must pass → ≥1 approve → merge commit
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
3. Merge via a merge commit (`--no-ff`). The published history is a chain of
   `Merge pull request #N` commits, so a squash would diverge from it.
4. If you're unsure → open a **Draft PR** first, ask for early feedback

**The PR description is where this project keeps its reasoning** — scope, what was
deliberately *not* changed, and the validation performed. There is no issue tracker
in use. See [claimtrace/docs/team.md](claimtrace/docs/team.md) §3.

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
| Wednesday | Group deep sync | per group | 30 min |
| Thursday | Cross-group alignment (API contracts) | one from each group | 20 min |
| Friday | Sprint Review + Retro + Planning | All 7 | 75 min |
| Friday | Workshop | All 7 | 3 hours |

Cross-group decisions are the ones about a **contract** — an API shape, a response
status, a boundary. Those get a document in `claimtrace/docs/` updated in the same PR.

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
| `/api/parse` | POST | Upload & parse a PDF or `.bib` |
| `/api/parse/{paper_id}` | GET | Get parse status |
| `/api/parse/{paper_id}` | PUT | Replace a synchronised `.bib` in place |
| `/api/parse/bib` | POST | Re-parse and return stored BibTeX entries |
| `/api/papers` | GET | List the paper library |
| `/api/papers/{paper_id}` | DELETE | Permanently delete a library record |
| `/api/papers/{paper_id}/claims` | GET | Extract claims and citation markers |
| `/api/verify/citation` | POST | Verify one claim against its source |
| `/api/verify/bib` | POST | Local bib × uploaded-PDF metadata check |
| `/api/audit` | POST | Bibliography audit (external publication records) |
| `/api/audit/{audit_id}` | GET | Get stored audit results |

Full schema: `backend/src/models.py`, `backend/src/audit_models.py` |
Interactive docs: `http://localhost:8000/docs` |
Contracts: [audit](claimtrace/docs/audit-contract.md) ·
[engine](claimtrace/docs/engine-verify-contract.zh-CN.md) ·
[citation comparison](claimtrace/docs/citation-comparison.zh-CN.md)

---

## Technology Stack

| Layer | Tech | Owner |
|-------|------|-------|
| PDF Parsing | OpenDataLoader (needs a Java runtime), PyMuPDF, pdfplumber | Parser |
| Reference Extraction | `reference_json_extractor` (APA 7, standard IEEE) | Parser |
| Embeddings | sentence-transformers (`all-MiniLM-L6-v2`) | Engine |
| Vector Index | FAISS (`faiss-cpu`) | Engine |
| LLM | Provider-agnostic (`engine/engine/llm_client.py`): OpenAI (`gpt-4o-mini`, default), DeepSeek (`deepseek-chat`), Gemini, Anthropic, Ollama | Engine |
| Publication Records | OpenAlex (primary) → Crossref (fallback), keyless REST | Backend |
| Backend | FastAPI + Uvicorn | Backend |
| Frontend | React 18 + Vite + TypeScript | Frontend |
| Extension | Chrome Manifest V3 | Frontend |
| CI/CD | GitHub Actions | all four |

Formula OCR (Nougat / Pix2Text) was planned in W3 and **is not implemented** — it appears
in no dependency file.

---

## Repository layout note: course deliverables vs. maintained docs

The files below are **course deliverables** — assessment artifacts submitted for
41129 Software Innovation Studio. They are kept as submitted and are **not**
maintained against the code. Do not treat anything in them as current, and do not
update them to match the implementation.

| File | What it is |
|------|-----------|
| `41129_PROJECT_IDEA_SHORTLIST.md` | A1 planning artifact |
| `Project pitch.pptx` | A1 pitch slides |
| `Project pitch8.21.pdf` | A1 pitch, exported |
| `Template of Project Pitch.pdf` | UTS-provided template |
| `Week 1 - Introduction.pdf` | UTS-provided course material |
| `team-charter.pdf` | UTS-provided charter template, **unfilled** |
| `ClaimTrace-Pitch-Script-and-QA.md` | Pitch script and Q&A prep |
| `ClaimTrace-Preparation-Plan.md` | The W1–W3 preparation plan. Its metric commitments are the origin of the benchmark bars in `claimtrace/engine/tests/benchmarks/CLAIM_PASSAGES.md`. |

Everything under `claimtrace/docs/` is the opposite: current, code-verified, and
expected to change with the code. Start at
[claimtrace/docs/README.md](claimtrace/docs/README.md).

---

## License

MIT
