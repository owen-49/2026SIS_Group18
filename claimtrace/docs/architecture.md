# ClaimTrace Architecture

> Last updated: 2026-08-07 | v0.1

---

## System Overview

```
                          ┌──────────────────┐
                          │  Chrome Extension │  Pair 3-B
                          │  (Overleaf Hover) │
                          └────────┬─────────┘
                                   │
                          ┌────────▼─────────┐
                          │  Web Dashboard    │  Pair 3-B
                          │  (React + Vite)   │
                          └────────┬─────────┘
                                   │ REST /api/*
                          ┌────────▼─────────┐
                          │  FastAPI Server   │  Pair 3-A
                          │  /parse /verify   │
                          │  /audit           │
                          └──┬──────────┬─────┘
                             │          │
                    ┌────────▼──┐  ┌───▼──────────┐
                    │  Parser   │  │  Engine       │
                    │  (Pair 1) │  │  (Pair 2)     │
                    │           │  │               │
                    │ PyMuPDF   │  │ FAISS + LLM   │
                    │ pdfplumber│  │ sentence-T5   │
                    └───────────┘  └───────────────┘
```

---

## Data Flow: Single Citation Verification

```
1. User uploads source PDF
     │
     ▼
2. Pair 1: parse_pdf(pdf_path) → ParsedPaper
     │  • extract_blocks → reorder_two_column → recover_paragraphs
     │  • element_extractor: formulas, tables, figures
     │  • reference_extractor: structured bibliography
     │
     ▼
3. Pair 2-A: build_index(parsed_paper.paragraphs) → FAISS index
     │
     ▼
4. User hovers \cite{key} in Overleaf
     │  → Pair 3-B extracts claim sentence + citation key
     │
     ▼
5. Pair 2-A: retrieve(claim, source_paper_index, k=5) → top passages
     │
     ▼
6. Pair 2-B: verify(claim, best_passages) → Verdict + Rationale
     │  • LLM prompt: SUPPORT / PARTIAL / CONTRADICT / NOT_FOUND
     │
     ▼
7. Pair 3-B: render popup with matched passage + verdict
```

---

## API Contracts

### POST /api/parse — Upload & parse a PDF

```
Request:  multipart/form-data { file: PDF }
Response: { paper_id, status, pages, paragraph_count, title? }
```

### GET /api/parse/{paper_id} — Get parse status

```
Response: { paper_id, status, pages, paragraph_count }
```

### POST /api/verify — Verify a claim

```
Request:  { claim: str, source_paper_id: str }
Response: {
  claim, verdict, confidence, rationale,
  matches: [{ passage_text, similarity, entailment_label, confidence }]
}
```

### POST /api/audit — Batch audit manuscript

```
Request:  { manuscript_id: str, source_paper_ids: [str] }
Response: {
  manuscript_id, total_citations, supported, partial,
  contradicted, not_found,
  results: [{ citation_key, claim, verdict, confidence, risk_level }]
}
```

---

## Technology Stack

| Layer | Technology | Rationale |
|-------|-----------|-----------|
| **PDF Parsing** | PyMuPDF (fitz) | Best text position extraction |
| **Table Extraction** | pdfplumber | Reliable table detection |
| **Formula OCR** | Nougat / Pix2Text (W3) | OCR-free LaTeX restoration |
| **Embeddings** | sentence-transformers (all-MiniLM-L6-v2) | Fast, local, good semantic quality |
| **Vector Index** | FAISS (IndexFlatIP) | In-memory, cosine similarity |
| **LLM (Verification)** | GPT-4o / Gemini 2.0 Flash | Strong entailment judgment |
| **Backend** | FastAPI + Uvicorn | Async, auto-docs, Pydantic validation |
| **Frontend** | React 18 + Vite + TypeScript | Fast dev, typed |
| **Extension** | Chrome Manifest V3 | Current standard |
| **CI/CD** | GitHub Actions | Free for public repos |

---

## Key Design Decisions

### 1. Two-Stage Retrieval (Paragraph → Sentence)
Paragraph-level embedding for recall, sentence-level re-ranking for precision.
Avoids the noise of sentence-only chunks and the low precision of paragraph-only.

### 2. Mock-First API Development
All API endpoints return valid (but stub) responses from Day 1.
Frontend and Extension can develop against real API contracts immediately.

### 3. Local-First Privacy
Source PDFs are processed locally. Only statistical summaries and
claim-passage pairs are sent to external LLM APIs.

### 4. Pair-Level Ownership
Each Pair owns their module end-to-end: code, tests, CI, documentation.
Cross-Pair integration happens through typed API contracts, not shared code.
