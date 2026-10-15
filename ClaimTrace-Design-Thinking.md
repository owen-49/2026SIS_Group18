# ClaimTrace — Design Thinking

**Group 18 · 41129 Software Innovation Studio · UTS · 13 October 2026**

ClaimTrace is a citation audit engine: a browser extension and web dashboard that check whether a
paper's claims are actually supported by the sources they cite. Team of seven, four working groups
(Backend · Frontend · Parser · Engine).

---

## 1. Empathise — who we are designing for, and how we know

### Scope

ClaimTrace sits at one moment in a researcher's workflow: the moment they want to know whether
something they, or a co-author, wrote is actually supported by the source it cites.

| In scope | Out of scope |
| --- | --- |
| Checking a bibliography against real publication records — does the reference exist, and do title, authors, year and venue agree? | Managing or formatting references (Zotero's job) |
| Checking a sentence against the source it cites — does the source actually support this claim? | Text-similarity and plagiarism checking (Turnitin's job) |
| Showing the evidence behind every result | Writing or rewriting the researcher's text |
| Working inside the editor, at the moment of writing | Judging authors, or acting as an authority on misconduct |
| Batch-checking a whole manuscript before submission | Retaining manuscripts beyond the working session |

### The three people we are building for

Recorded in `docs/user-research/personas.md`:

**P1 — the anxious first author.** A third-year CS PhD student writing a first-author paper for a
top conference, responsible for Related Work and Discussion sections written by three co-authors.
They do not fully trust citations they did not write, and have no time to download and check every
PDF; moving between the editor, a reference manager and a PDF reader breaks their train of thought;
and a reviewer once pointed out in a rebuttal that a citation *actually concluded the opposite* of
what the paper claimed. Forty-eight hours before a deadline they find thirty-plus unverified
citations, and — in their words — "can only let most of them slide on gut feel."

They asked for two things: hover in Overleaf and know whether a citation is right, without leaving
the editor; and run the whole paper at once and tell me the three citations most in need of human
review.

**P2 — the supervising PI.** An associate professor with five PhD students, gating every draft in
fragmented time. They cannot verify each citation themselves; they have seen student references
pasted from ChatGPT; and they want evidence rather than conclusions so they can give specific
feedback. Their scenario: an eight-page draft and thirty minutes. They asked for a risk-ranked
report with the doubtful citations marked and the source evidence attached, so they can screenshot
it straight to the student.

**P3 — Reviewer 2.** A conference reviewer reading five to ten submissions a year. They suspect a
claim over-interprets its source, but verifying it costs time they do not have, and a review
comment has to be specific and citable rather than a vague "references are not rigorous." They
asked to see the claim and the cited passage side by side, to judge in thirty seconds whether the
author distorted the source.

### The one thing all three said

All three personas ask for the same thing, and the personas document records it as their shared
insight: **they want to see the source evidence, not an AI conclusion.** That single sentence
became the product's central design rule (Section 2): every verdict ships with the passage it is
based on.

### How these personas were built — and the honest limit

They are **synthesised personas**. They were compiled from desk research into the published
evidence about citation error, and from our own experience: all seven of us write papers, and every
one of us has hit this exact moment. The interview round that would test them is planned and
written down — five researchers who recently submitted to a top venue, with the protocol,
recruiting channels and output format in the preparation plan — but **it has not yet been run**. We
state that plainly because it is the largest open item in this document (Section 6): today the
personas are hypotheses with strong supporting evidence, not findings from sessions.

### Why we believe the pain is real — the published evidence

From our market analysis (`ClaimTrace-Market-Analysis.md`), which cites each source:

- **One in six quotations is wrong, and half of those errors are serious** — 16.9% of quotations
  incorrect (8.0% major) across 46 studies and roughly 32,074 quotations, with no improvement over
  forty years (Baethge & Jergas 2025).
- **The people downstream are not catching it.** Reviewers missed two-thirds of major errors in a
  controlled study, and in a study of 607 BMJ reviewers the mean number of planted errors found was
  three of nine. A 2023 BMJ analysis concludes that the duty to audit cited literature rests with
  the citing author — and proposes exactly this class of tool.
- **It is getting worse, not better.** Fabricated citations rose more than twelvefold in the
  samples tracked between 2023 and early 2026, and retracted work keeps being cited for years after
  retraction.
- **AI writing assistants fabricate references that look real**: GPT-4o produced fabricated
  references in 19.9% of cases and bibliographic errors in 45.4% of the references that were real.

The pain is documented, measured, and — the part that matters for design — *unattended*: nothing in
a researcher's existing tool chain is responsible for checking the sentence against its source.

---

## 2. Define

### The problem, stated once

*For researchers co-writing a conference paper in Overleaf, verifying that a co-author's cited
source actually says what the claim says is slow, manual and interruptive — so it is not done
before submission, and the errors surface after publication, when correcting them is someone
else's problem.*

### The gap

Every established tool checks something. Reference managers check the record's metadata. Similarity
checkers compare strings of text. Citation-intent platforms classify how *other papers* cited a
work. Reference checkers confirm that a record exists. **None of them checks the sentence** — does
*this* source support *this* claim? That gap is the product.

### How might we

1. **How might we** make verification instant and non-interruptive — inside the editor, at the
   moment of writing?
2. **How might we** check a whole bibliography at once, and rank what deserves a human's attention?
3. **How might we** be honest about uncertainty, so the tool is trusted exactly when it matters?

### The four design principles that came out of Define

**1. Show the evidence, not just the verdict.** Every result carries the matched source passage,
page and similarity, so the researcher can overrule the tool. The four verdicts for a claim are
Supported, Partially supported, Contradicted and Not found; "Partially supported" exists precisely
to name the common failure of overstating a source or dropping a qualifier, rather than forcing it
into a yes or no.

**2. A failed check is never reported as a negative finding.** The Batch audit reports one of five
states, and the distinction between the last two is the most important thing in the product:

| State | Meaning |
| --- | --- |
| `VERIFIED` | The record was found and the checked fields agree |
| `METADATA_MISMATCH` | The record was found and a field disagrees |
| `NEEDS_REVIEW` | The lookup was inconclusive, or two records are equally plausible |
| `NOT_FOUND` | The check **ran** and found nothing |
| `LOOKUP_FAILED` | The check **could not run** — reported as *not checked*, never as "does not exist" |

The dangerous output of an audit tool is not a wrong answer; it is a reassuring one, or an
accusation the tool cannot support. A researcher who is told "not found" and believes it may
delete a real citation; a researcher told "lookup failed" knows to check by hand.

**3. Constrain the model.** The language model's only job is to classify the relationship between
two passages the system has already retrieved from real text. It never generates a reference from
memory, and the researcher supplies their own provider credentials per request — the product holds
no shared key and stores no key. If the model is unavailable or the comparison is incomplete, the
result is an explicit failure state, never a guessed verdict.

**4. Never block the writing flow.** The Overleaf hover card is built from local data — no network
request and no spinner on hover — and the batch audit runs as a background pass over the reference
list rather than holding up the editor.

---

## 3. Ideate

### From problem space to a chosen concept

Three project ideas were scored against pain, verifiability of value, technical risk,
differentiation, delivery scope and evidence potential: a personal health-data interpreter, a
campus accessibility tool, and ClaimTrace. ClaimTrace won on two criteria in particular — its value
is *measurable* (a passage either supports a sentence or it does not, so the team could be held to
a number), and the problem itself is documented in the literature rather than assumed. The idea
shortlist also named its own riskiest assumption up front: retrieving the right passage from
double-column, equation-dense PDFs without inventing one. That assumption is answered in the
product by two-column reading-order recovery and cross-line hyphenation repair in the parser, and
by the rule that retrieval results are always shown rather than summarised.

### User stories (`docs/user-research/user-stories.md`)

| ID | Story (abridged) | Priority | In the product today |
| --- | --- | --- | --- |
| US-01 | Upload a source paper PDF and have it parsed into structured paragraphs | P0 | Shipped |
| US-02 | Hover a citation in Overleaf and see the source passage it points to | P0 — core differentiator | Partially shipped — hover shows the citation, its bibliography entry and its location, marked "Not checked"; the passage card shipped on 18 September and was disabled on 19 September, when the extension was made Audit-only |
| US-03 | Submit a claim and get a support verdict against its cited source | P0 | Shipped |
| US-04 | Upload a `.bib` and cross-check it against the source PDFs | P0 | Shipped (checks the `.bib` against user-supplied PDFs; explicitly not existence proof) |
| US-05 | Check a manuscript's bibliography against external publication records | P1 | Shipped — Batch audit, five states |
| US-06 | See the evidence behind every verdict | P1 — foundation of trust | Shipped in both flows |
| US-07 | Manage a paper library so a source is parsed once | P1 | Shipped |
| US-08 | Reviewer fast-checks a submission | P2 | Partial — the Verify flow works on any manuscript; no reviewer-specific view |
| US-09 | Export a shareable audit report | P2 | Not built |
| US-10 | Share a team paper library | P2 | Not built |

### The journey we designed for

| Stage | Without ClaimTrace | With ClaimTrace |
| --- | --- | --- |
| Notice a doubtful claim | Open a mental "to check" list that never gets checked | Hover the `\cite{}` in Overleaf |
| Check the source | Find the PDF, download it, Ctrl+F, read around the hit — minutes per citation | The Verify workspace shows the cited passage with a four-way verdict on it; in Overleaf the card identifies the citation and its entry, marked not checked |
| Decide | Gut feel; usually "let it slide" | A four-way verdict with the passage beside it — the researcher still decides |
| Whole bibliography | Never checked at all | Batch audit against OpenAlex, then Crossref; five states with a findings list |
| Before submission | Hope | The short list of references that genuinely need a human |

### What we deliberately did not build

An early version of US-05 described a *semantic* batch audit that ranked claims by risk. That flow
was removed from the backend — Audit is now a bibliography check — and the user stories were
revised on 21 September to match the product rather than the other way round. US-08, US-09 and
US-10 (reviewer workspace, report export, shared team library) are deferred: each is valuable, none
is on the critical path to a trustworthy core, and the priority matrix rates them below the
verification flows.

---

## 4. Prototype

### What exists today

Four working parts, all in one repository:

1. **Web dashboard** (React 18 + Vite + TypeScript). A *Batch audit* page — five-state result
   counts, a findings list, and a detail panel per reference showing the input metadata, the
   matched publication, the field-by-field checks and every lookup attempt. A *Verify claims* page
   — the manuscript and the cited article side by side, select a cited sentence, and get the
   matched evidence and verdict. A help page, and a five-step guide for loading the extension.
2. **Chrome extension** (Manifest V3, version 0.4.0). Reads the `.bib` from Overleaf, uploads it,
   and runs the batch audit; the hover card on a `\cite{}` shows the citation, its bibliography
   entry and its location, marked not checked — the extension is Audit-only — and times itself
   locally. A side panel lists citations and papers with "Check references" and "Check a
   manuscript instead".
3. **Backend API** (FastAPI). Document parsing for PDF and `.bib` uploads, a paper library,
   citation-claim extraction, the Verify routes, the `.bib`-vs-PDF cross-check, and the Audit route
   that persists its reports (`contract_version: 2`).
4. **Engine**. Reference-text parsing into structured fields, the identity rule that decides
   whether a candidate record is the same work (title, author, year and venue agreement, with an
   explicit year tolerance and explicit abstention paths), the OpenAlex → Crossref provider chain,
   and retrieval plus entailment for Verify (sentence embeddings with a local FAISS index).

Persistence is file-based — one directory of JSON per paper, no database. That was a deliberate
choice for a seven-person course project: there is no service to run, artifacts can be inspected
and diffed, and the parse output doubles as test fixtures.

### Prototype iterations

| When | What changed |
| --- | --- |
| W4–W9 | Mock pipeline first (the dashboard still ships a demo mode with sample data and a "Mock API active" pill), then the real parser and real HTTP integration across four groups |
| 19 September 2026 | End-to-end acceptance on the real Overleaf with the real extension and a real backend — passed: the plugin's external reference lookups, and the citation display (a citation on its own line showed its surrounding sentence, not only `\cite{}`). The extension was made Audit-only the same day, disabling the hover card's source passage, which had shipped on 18 September |
| Late September | The metadata provider chain replaced the earlier Google Scholar lookup, giving the audit an OpenAlex-first, Crossref-fallback design that needs no key |
| October | Researchers bring their own AI provider credentials (17 providers, keys held only for the lifetime of the request); the provider expansion (PR #60) removed the last feature that would have implied a shared team key |
| October | Measurement: the audit and verify benchmark harnesses that produce the numbers in Section 5 |

### Screenshots

> **[Screenshot 1 — Batch audit results]** *To capture:* the `/audit` page with a real manuscript
> loaded: the five-state count tiles, the findings list filtered to `METADATA_MISMATCH`, and the
> detail panel for one reference showing field checks and lookup attempts.

> **[Screenshot 2 — Verify claims]** *To capture:* the `/verify` page with a claim selected in the
> manuscript, the cited article beside it, the verdict badge and the matched source passage.

> **[Screenshot 3 — Overleaf hover card]** *To capture:* the real Overleaf editor with a hover card
> open on a `\cite{}`, showing the citation, its bibliography entry and the "Not checked" badge —
> the extension is Audit-only and shows no source passage.

> **[Screenshot 4 — Extension side panel]** *To capture:* the side panel open on a loaded project:
> the Citations tab with a "Check references" result.

The dashboard's demo routes (`/audit/example`, `/verify/example`) render sample data with the mock
API active. Any screenshot taken there must be labelled as demo data; Screenshots 1 and 2 should
come from a real parse.

---

## 5. Test

### Three layers of testing, answering three different questions

| Layer | Question it answers | State on 13 October 2026 (main) |
| --- | --- | --- |
| Automated suites (CI) | Does the code still do what we said it does? | Backend 523 tests · Engine 352 · Parser 100 (+2 skipped, missing Java runtime) · Extension 49 · Frontend integration suite (Playwright, mocked backend) last recorded at 47. All green. |
| Live acceptance (real editor, real providers) | Does it work end to end, for a person? | Real Overleaf + external lookup acceptance passed on 19 September 2026. DeepSeek live Verify acceptance: 12 passed, 0 failed on 11 October 2026. |
| Measurement harnesses (not tests; never in CI) | How accurate, and how fast? | Audit replay 36 of 39 constructed bibliography cases + 3 of 3 PDF cases. Timing curve measured. Verify accuracy awaiting annotation. |

### What the measurement says so far

- **Audit accuracy.** Constructed cases with frozen provider responses: 36 of 39 bibliography-form
  cases and all three PDF-form cases pass, with field-level checks (title, authors, year, venue)
  verified per case. The three that fail are red on a recorded-fixture mismatch — the case expects
  an ambiguous-record outcome and the captured provider bytes say not-found — and are recorded for
  a person to decide rather than silently edited to green.
- **Audit time.** N-scaling over 5, 10, 20, 40 and 80 entries: median 0.45 s, 0.83 s, 1.66 s,
  3.31 s, 6.57 s — linear, about 0.055 s per entry, matching the serial design. We report this as a
  baseline and set no pass line for time; the number exists to show the shape of the cost, not to
  certify a speed.
- **Verify time.** The live end-to-end run measured a mean of 1.37 s per case (default mode) and
  1.26 s (low thinking) across twelve executions. The harness documents its own limit: six cases
  prove the wiring, they do not establish an accuracy figure.
- **Verify accuracy.** Not yet measured, and we are explicit about why: the instrument is built and
  the candidate set is harvested — 103 real claim/source pairs, ready on a labelling worksheet —
  but the labels are human work that has not been done. Two people annotate independently, the
  merge reports raw agreement and Cohen's kappa, and only the agreed pairs become the benchmark.
  The success bar is fixed in advance: accuracy ≥ 0.80, F1 ≥ 0.85, kappa ≥ 0.70.

### What testing has found

Real defects, found by tests rather than by users:

- **Parser:** an author list ending in a run of initials ("Victor O.K. Li") was split at the first
  initial, producing an author called "Victor O" and a title of "Li". Found by running the parser
  over all 155 extracted reference entries, not by a hand-written case.
- **Engine:** seven references in a 140-reference corpus took their year out of an arXiv
  identifier — `1911.03587` read as the year 1911 — and because the identity rule rejects a
  candidate whose year differs by more than one, each of those references could never match its
  true record. Fixed by testing whether a year candidate sits at the start of an arXiv identifier;
  the fix changed seven years and no other field in the corpus, and shipped with four tests built
  from the corpus text itself.
- **Frontend:** the mocked-browser acceptance found an AI-provider workspace field that Chrome
  rejected but Node accepted, and a validation error that arrived with a code but no message. Both
  were fixed with regression tests; the error-message one mattered because "invalid request" with
  no reason is exactly the kind of output that erodes trust in an audit tool.
- **Backend:** paper deletion was made recoverable and safe under concurrent requests.

### Safety invariants are test criteria, not scores

The audit harness asserts three properties on every result, as pass/fail rules rather than
accuracy percentages — a violation is a bug, never a low score:

1. `NOT_FOUND` requires that every lookup attempt actually completed and found nothing, and that at
   least one attempt was made.
2. `LOOKUP_FAILED` requires at least one attempt to have failed for a reason other than "not
   found" — so a partial failure can never silently degrade into a negative finding.
3. A reference with no searchable title must produce no lookup attempts at all, and be reported for
   review rather than searched for with nothing.

---

## 6. Analysis

### What the design thinking changed

The two decisions that shaped the product most both came from the empathy work, not from a feature
list. "Show me the source evidence, not a conclusion" — the thing all three personas said — became
the rule that no verdict is a result without its passage; the UI shows what supports the answer
even when the answer is "not found". The second came from asking what a *wrong* answer would do to
a person: a false "this reference does not exist" is an accusation, and a researcher who believes
it may delete a real citation. That is why `LOOKUP_FAILED` exists as a separate state and why the
harness treats converting a failure into a negative finding as a defect rather than an error rate.
Neither principle would have survived a purely feature-driven process, because both make the
product *less* conclusive.

### What we would do differently

1. **Talk to strangers sooner.** Our personas are synthesised from desk research and our own
   experience. That was enough to find a real problem — we all live it — but it cannot tell us what
   a supervisor with five students actually wants, and every persona detail remains a hypothesis
   until the planned interview round runs. The course's own success criterion ("three real
   researchers try the product") is still open and unassigned, and that is the first thing we would
   fix with more time.
2. **Do not keep documents that describe an aspiration as if it were process.** An unused
   Jira-workflow document and an unfilled team-charter template both survived into the repository
   and cost time later, because they described a process that had never happened. They are
   replaced by a short record of what is actually practised: pull requests with scope-and-validation
   descriptions, directory-level ownership, and contracts in `docs/`.
3. **Verify documentation against code, not against other documents.** Three gaps that had already
   been closed stayed listed as open for weeks, and work was assigned twice on that basis. The
   project's actual documentation failure mode was under-reporting completion.
4. **Correct our own evidence in public.** Our pitch carried four figures that the later market
   analysis retracted — a fused statistic from a vendor blog, a market-size range that competing
   vendors disagree on by a factor of three, a "survey" that turned out to be a conference poster,
   and an acquisition price quoted net of cash. We kept the figures that hold and wrote the
   retraction into the analysis. Doing this after the pitch was uncomfortable and it is the single
   habit we would start earlier.

### Open items the next iteration must close

| Item | Why it matters | State |
| --- | --- | --- |
| Real-user validation (≥ 3 researchers) | Every persona is still a hypothesis | Interview plan written; unowned |
| Verify accuracy on 103 annotated pairs | The product's central claim, measured on real claims | Worksheet built; labels outstanding |
| Parser Recall@5 on held-out PDFs | Retrieval quality, the riskiest original assumption | Instrument built; labels outstanding |
| Three red audit fixture cases | Recorded provider bytes disagree with the constructed expectation | Needs a human decision |
| Regenerate the accuracy dashboard | The committed dashboard predates the current fixtures | Pending |

### What we are taking away

The most valuable outputs of the design thinking were two constraints that made the product
smaller: show the evidence, and never turn a failed check into a negative finding. Both are
statements about what the tool must *not* do. For a tool whose job is to be trusted about other
people's work, that turned out to be the right way round.

---

## Additional Notes

**Where each claim in this document is evidenced.**

| Claim | Source |
| --- | --- |
| Personas, shared insight, interview plan | `claimtrace/docs/user-research/personas.md`; `ClaimTrace-Preparation-Plan.md` |
| User stories and their revision | `claimtrace/docs/user-research/user-stories.md` |
| Problem statistics | `ClaimTrace-Market-Analysis.md` (§2), with each study cited in place |
| Five-state contract, failure rule | `claimtrace/docs/audit-contract.md`; `claimtrace/docs/README.md` |
| Design decisions, scope, gaps | `claimtrace/docs/architecture.md` |
| Acceptance run, 19 September 2026 | `claimtrace/docs/audit-live-acceptance/live/overleaf-external-acceptance-2026-09-19.md` |
| DeepSeek live Verify acceptance | `claimtrace/docs/verify-acceptance-deepseek-live.md` |
| Audit accuracy and timing numbers | `claimtrace/docs/accuracy-baseline/`; `claimtrace/docs/team.md` §3 |
| Team structure and ownership | `claimtrace/docs/team.md` |

**Two notes for the reader.** The persona document is written in Chinese; quotations in Section 1
are translated. The screenshots in Section 4 are placeholders to be filled from the running
product — any image taken in the dashboard's demo mode should be labelled as demo data.
