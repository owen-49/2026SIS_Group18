# User Stories

> Related personas: see [personas.md](personas.md).  
> Priority: **P0** = MVP must-have (core loop for the 12-week demo); **P1** = important, ship if possible; **P2** = nice-to-have, deferrable.

---

## Feature Groups Overview

```
A. Document Ingestion   B. Citation Verification   C. Metadata Check   D. Bibliography Audit
   ├ US-01 Upload PDF      ├ US-02 hover             ├ US-04 local bib     ├ US-05 audit
   │                       ├ US-03 verdict           │   × PDF check       │
   └ US-07 library         └ US-06 evidence          └                     └ US-09 export report
```

> Revised 2026-09-21. The original US-05 described a semantic *batch* audit that ranked
> claims by risk. That flow was removed from the backend; Audit is now a bibliography
> check. US-04 and US-06 were adjusted for the same reason. Numbering is unchanged —
> `extension/src/content.js` and `extension/hover-card.test.cjs` cite US-02 by number.

---

## P0 — MVP Core (must ship)

### US-01 · Upload and parse a source paper PDF

> **As a** researcher (P1), **I want** to upload a source paper PDF and have it parsed into structured paragraphs, **so that** the system can run citation verification against it.

- **Priority**: P0
- **Persona**: P1 PhD student (primary), P2 supervisor
- **Acceptance Criteria**:
  - [ ] Accept PDFs up to 50MB; return a clear error (not a 500) for non-PDF files
  - [ ] Return `paper_id`, paragraph count, and page count after parsing
  - [ ] Correctly recover two-column reading order (no column mixing)
  - [ ] Repair cross-line hyphenation (`repre-\nsentation` → `representation`)
  - [ ] Parse status queryable by `paper_id`
- **Story Points**: 8

---

### US-02 · Hover a citation in Overleaf to see the source passage

> **As a** researcher (P1), **I want** to hover over `\cite{...}` in Overleaf and see the original passage it points to, **so that** I can verify a citation without leaving my writing flow.

- **Priority**: P0
- **Persona**: P1 PhD student (core)
- **Acceptance Criteria**:
  - [ ] The browser extension identifies `\cite{key}` and captures the hover event
  - [ ] The popup shows the matched source passage (highlighted) on hover
  - [ ] The popup displays a verdict badge (🟢/🟡/🔴)
  - [ ] End-to-end latency < 1s (on an already-indexed paper)
- **Story Points**: 13

---

### US-03 · Verify whether a claim is supported by its cited source

> **As a** researcher (P1), **I want** to submit a paper claim and get a verdict of supported / partially supported / contradicted / not found, **so that** I know whether the citation is accurate, overstated, or misquoted.

- **Priority**: P0
- **Persona**: P1 PhD student, P3 reviewer
- **Acceptance Criteria**:
  - [ ] Return a four-way verdict: `SUPPORT` / `PARTIAL` / `CONTRADICT` / `NOT_FOUND`
  - [ ] Each verdict includes a confidence score and the matched source passage
  - [ ] Semantic matching handles paraphrase (different wording, same meaning)
  - [ ] The verdict includes a human-readable rationale
- **Story Points**: 13

---

### US-04 · Upload a .bib file and validate its metadata

> **As a** researcher (P1), **I want** to upload a `.bib` file and cross-check it against the real information printed on the source PDFs, **so that** I can catch wrong years, garbled titles, and DOIs pointing to the wrong paper in my bibliography.

- **Priority**: P0
- **Persona**: P1 PhD student
- **Acceptance Criteria**:
  - [ ] Parse the `.bib` file into structured entries (title/authors/year/venue/DOI)
  - [ ] Return per-field `MATCH` / `MISMATCH` / `BIB_MISSING` / `PDF_MISSING`
  - [ ] Support common BibTeX features (`@string` macros, `#` concatenation, LaTeX escapes, author-name normalization)
  - [ ] Degrade gracefully when a source PDF is missing (return `PDF_MISSING`, not a crash)
- **Story Points**: 8

> This checks the `.bib` against **a PDF the user supplied** — it never contacts an
> external service. It is therefore *not* existence proof: a wrong year that the cited
> PDF also prints still matches. US-05 is the external check. Keep the two distinct in
> the UI so a `MATCH` here is not read as "this reference is real".

---

## P1 — Important (ship if possible)

### US-05 · Check a manuscript's bibliography against external publication records

> **As a** researcher (P1), **I want** to upload or select a bibliography — a manuscript's reference list or a `.bib` — and have every entry checked against real publication records, **so that** I catch fabricated, misattributed or garbled references before submission without hunting down each cited PDF myself.

- **Priority**: P1
- **Persona**: P1 PhD student, P2 supervisor
- **Acceptance Criteria**:
  - [ ] Accept either an uploaded `.bib` or a manuscript PDF; **no source PDFs required**
  - [ ] Return a per-entry state: `VERIFIED` / `METADATA_MISMATCH` / `NEEDS_REVIEW` / `NOT_FOUND` / `LOOKUP_FAILED`
  - [ ] Show both values for each field difference, and link the matched record
  - [ ] Report `LOOKUP_FAILED` as "not checked" — never as "does not exist"
  - [ ] An entry with nothing found is reported as not found, **not** as fabricated
- **Story Points**: 8

---

### US-06 · See the source evidence behind every verdict

> **As a** researcher (P1/P3), **I want** every result to come with its evidence, **so that** I can judge whether the tool got it right rather than trusting the label blindly.

- **Priority**: P1
- **Persona**: All (this is the foundation of trust)
- **Acceptance Criteria**:
  - [ ] **Verify (US-03)**: show the matched source passage beside the verdict, not just the label
  - [ ] Annotate the passage with its location (page / section / citation key)
  - [ ] Let the user jump to the corresponding location in the source PDF
  - [ ] **Audit (US-05)**: the evidence is the retrieved record — its URL, provider and query time — plus the field differences. Audit has no source passage and must not show one.
- **Story Points**: 5

---

### US-07 · Manage a paper library (reuse parsed papers)

> **As a** researcher (P1), **I want** uploaded papers to be saved in a library and reused without re-uploading, **so that** citing the same source across multiple manuscripts doesn't require re-processing.

- **Priority**: P1
- **Persona**: P1 PhD student, P2 supervisor
- **Acceptance Criteria**:
  - [ ] Parsed papers persist across restarts
  - [ ] The library supports listing and querying uploaded papers
  - [ ] A paper can be reused for multiple verifications
- **Story Points**: 5

---

## P2 — Nice-to-have (deferrable)

### US-08 · Reviewer fast-checks a submission

> **As a** reviewer (P3), **I want** to quickly check whether a submission's core claims cite their sources accurately, **so that** I can write evidence-backed review comments.

- **Priority**: P2
- **Acceptance Criteria**:
  - [ ] Support importing a submission PDF and auto-extracting its reference list
  - [ ] Run a bibliography check (US-05) over the whole reference list without needing the cited PDFs
  - [ ] Report identity and metadata outcomes per entry; do not present "not found" as evidence of fabrication
  - [ ] Optionally run single-claim Verify (US-03) on selected claims
- **Story Points**: 8

---

### US-09 · Export an audit report

> **As a** researcher (P1/P2), **I want** to export the audit result as a shareable report (Markdown/PDF), **so that** I can send it to co-authors or my supervisor for discussion.

- **Priority**: P2
- **Acceptance Criteria**:
  - [ ] Export the bibliography outcomes with the field differences and record links behind them
  - [ ] Include a suggested correction for each metadata difference
  - [ ] State clearly that "not found" is not an accusation
- **Story Points**: 3

---

### US-10 · Share a team paper library

> **As a** co-authoring team (P1), **I want** to share a paper library among the team, **so that** citation-verification results can be reused and duplicated effort avoided.

- **Priority**: P2
- **Acceptance Criteria**:
  - [ ] Multiple users can access the same library
  - [ ] Verification results can be shared with teammates
- **Story Points**: 8

---

## Priority Matrix (value × cost)

| Story | Value | Cost | Decision |
|-------|:---:|:---:|----------|
| US-01 Upload & parse PDF | High | Med | **P0 ship** |
| US-02 Hover verify | Very high | High | **P0 ship** (core differentiator) |
| US-03 Claim verdict | Very high | High | **P0 ship** (core value) |
| US-04 Local bib × PDF check | High | Low | **P0 ship** (low cost, high payoff) |
| US-05 Bibliography audit | High | Med | **P0 ship** (needs no source PDFs) |
| US-06 Evidence view | Very high | Low | P1 prioritize (trust foundation) |
| US-07 Paper library | Med | Low | P1 prioritize |
| US-08 Reviewer scenario | Med | High | P2 defer |
| US-09 Export report | Med | Low | P2 defer |
| US-10 Team sharing | Med | High | P2 defer |
