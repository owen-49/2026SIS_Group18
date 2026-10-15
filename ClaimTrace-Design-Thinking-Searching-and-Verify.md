# ClaimTrace — Design Thinking: Searching Engine and Verify Function

**Group 18 · 41129 Software Innovation Studio · UTS · 15 October 2026**

This document applies the six-step design thinking process to the two Engine subsystems only:

| Subsystem | The question it answers | Code |
| --- | --- | --- |
| **Searching engine** | Does the cited work exist in the publication record — and does the manuscript describe it correctly? | `engine/engine/` — `reference_text.py`, `openalex_lookup.py`, `crossref_lookup.py`, `metadata_lookup.py`, `identity.py`, `title_matching.py` |
| **Verify function** | Does the cited source actually say what the sentence claims? | `engine/engine/` — `source_resolver.py`, `retriever.py`, `embedder.py`, `verifier.py` |

The whole-product design thinking is in `ClaimTrace-Design-Thinking.md`. This is the engineering-level
pass on the two parts the Engine group owns: what each was designed against, what was tried and
rejected, what exists today, what the tests measured, and what is still open.

---

## 1. Empathise

### The moment each subsystem exists for

**Searching engine.** A supervisor has thirty minutes and an eight-page draft. They are not going to
find thirty PDFs; they are going to look at the reference list and ask, per entry, *is this real, and
is this entry describing it correctly?* That is the moment the audit serves.

But the literature review turned up a sharper, less comfortable requirement. Academia already knows
citations are wrong — 16.9% of quotations, 8.0% seriously so, across 46 studies and ~32,074
quotations, flat for forty years. What the design had to answer was not "how do we find errors" but
**"what happens when we are the ones who are wrong."** Telling a researcher that a colleague's
reference *does not exist* when the truth is that our lookup was throttled is not a neutral error —
it is the seed of a false accusation, and it is unrecoverable in a way that a missed error is not.
An earlier version of the product had exactly this failure shape available to it. The five-state
audit contract exists to make it impossible.

**Verify.** The 2 a.m. moment: the sentence is written, the citation is attached, and the doubt is
*does that paper actually say this?* Every persona in the user research asks for the same thing at
this moment — not a label, but **the passage**. The primary persona (an anxious first author who
does not trust citations they did not write) and the secondary persona (a PI who wants to give
specific feedback) both converge on it, and the long-term reviewer persona wants claim and passage
side by side for the same reason: a reviewer who cannot quote the source cannot put the concern in
a review.

That convergence became the shared insight the whole product is designed around: **show the source
evidence, not the conclusion.** For the Verify function it is a hard requirement, not a style
choice: a verdict without the passage it came from is exactly the AI conclusion the personas said
they do not trust.

### The component as a user

Both subsystems are also consumers of other people's outputs, and their interfaces are consumed by
other groups. A design that only considers the end user forgets that an enum is a promise.

| Consumer | What it does with the output | What the design therefore owes it |
| --- | --- | --- |
| Backend audit path | Persists each reference's state and its lookup attempts; its own validator rejects `not_found` unless every attempt is itself `not_found` | The engine's rule must be the same rule, applied where the attempts are made — not a second, weaker copy |
| Backend Verify path | Maps the verdict onto `VerdictEnum`; returns non-judged outcomes as HTTP 200 with a null judgement | The verdict set is closed; "not judged" must never arrive dressed as a verdict |
| Dashboard (`VerdictBadge.tsx`, `types/api.ts`) | Indexes a label map with no runtime guard | A fifth verdict would render `undefined` and a bogus CSS class — silently |
| Extension (Overleaf hover) | Renders the hover card and the audit panel from `/api/parse` and `/api/audit`; it does not call `/api/verify` | The card is built from local data with no request on hover — so if Verify is wired back into it, the evidence must already be in the payload |
| Parser | Supplies the passages and the reference text that both subsystems consume | The engine may depend on the parser's *output*, never on its package |

### An honest note on method

The personas are **synthesised** — from the published literature and from the team's own experience
as researchers. `docs/team.md` records that the interview round with five external researchers is
planned and has not been run. Everything in this section is a hypothesis with a stated origin; the
interview round is the first open item in Section 6, and it is the same open item the whole-product
document carries.

---

## 2. Define

### The two problems, stated precisely

**Searching engine.** Given one reference as it actually appears in a manuscript — a human-formatted
string from a PDF or a BibTeX entry, with no guaranteed structured fields — decide whether that work
exists in the public record and whether the manuscript's metadata agrees with it; and when the answer
is not a clean yes or no, say **which kind of no it is**.

**Verify function.** Given a claim and the source it cites, decide whether the source supports the
claim, and show the passage the decision rests on — or report, explicitly and visibly, that the
comparison could not be made.

### Design constraints — the rules that bound both

| Constraint | Where it comes from | What it forbids |
| --- | --- | --- |
| **A failed check is never a negative finding** | The false-accusation asymmetry above | `NOT_FOUND` may only mean "searched, completed, found nothing"; a throttle is `LOOKUP_FAILED` |
| **The identity decision is structural, never a weighted score** | A live provider query returns records *built to look like* the cited work | Any rule that a copy can satisfy — similarity above a threshold, a score sum |
| **A verdict exists only when the model actually judged** | The closed verdict set with three external consumers | A fifth verdict; a default label; `NOT_FOUND` used as "I could not tell" |
| **Every result carries its evidence** | The personas' shared insight | A verdict without a passage; an audit state without its lookup attempts |
| **Ambiguity goes to a person** | The tool is advisory, not an authority | Silently picking the better-ranked of two plausible records |
| **The engine imports neither the backend nor the parser** | Directory-level ownership; four groups work in four directories | Reaching across a package boundary for convenience |

### How might we…

1. Decide that a record *is* the cited work — when a record designed to impersonate it is also
   returned — without a similarity score that the impersonation can satisfy?
2. Tell "it is not there" apart from "we did not manage to look", when every layer between the
   reference text and the provider can fail in its own way?
3. Judge a claim against a source when academic prose restates rather than repeats — the exact
   thing keyword search cannot see?
4. Show the evidence for a model's judgement when the model is the one component that could
   invent the evidence?

---

## 3. Ideate

### Searching engine — options considered

| Option | Outcome | Why |
| --- | --- | --- |
| Scrape a citation index (the first version read Google Scholar) | **Replaced** | No API contract, session-based blocking, bounded retry loops. OpenAlex and Crossref are documented REST APIs, both work keyless, and OpenAlex indexes the preprints the corpus actually cites |
| One provider (the most authoritative) | **Rejected** | The chain is injected and ordered OpenAlex → Crossref; the second provider costs nothing when the first resolves, and covers what the first's ranking hides |
| Rank candidates by similarity, take the best | **Rejected** | A live query for a well-known title returns 2025 records by an unrelated organisation carrying the real title and author list verbatim. A score can be raised by copying text; a structural filter on venue, year and type cannot be satisfied by copying |
| A fuzzy near-title tier with tunable thresholds | **Built, measured, removed** | Swept across its whole usable range it never once decided a case. A constant that nothing depends on cannot be measured, so it was deleted instead of tuned. It was replaced by a rule with no constant in it: two records that share an informative title token are *ambiguous* — a question handed to a person |
| Tune `YEAR_TOLERANCE` to a "safe" middle | **Rejected — pinned from both sides instead** | Measured: 0 rejects a correct record (8 of 13 cases, recall at 50%); 2 admits a superseded conference version of the same work. Only 1 does neither |
| Require an identifier (DOI / arXiv) before matching | **Rejected as a requirement** | Only 53 of the 140 corpus references carry either. Identifiers are instead a *pre-pass* when present: it bypasses the year veto (publishers date the same DOI differently) but not the type filter |

### Verify — options considered

| Option | Outcome | Why |
| --- | --- | --- |
| Ask a model to read the whole paper and answer | **Rejected** | Unbounded context, unverifiable output, and precisely the fabrication failure the product exists to catch |
| Keyword / Ctrl+F search of the source | **Rejected** | Paraphrase is invisible to it, and paraphrase-invisibility is the failure mode |
| Retrieve semantically, return the label without the passage | **Rejected** | Contradicts the shared insight, and makes the judgement unauditable by the person it is for |
| A fifth verdict meaning "could not judge" | **Rejected** | Three consumers treat the enum as closed; a fifth member fails silently in the badge and raises far from its cause in the backend. Abstention is expressed by `VerificationStatus`, never by a new verdict |
| Report the model's self-reported confidence as a probability | **Demoted** | `confidence` is a coarse band, documented as *not* a probability the model reported, and is `0.0` on every failure — "a failure must not imply certainty" |
| Two-stage retrieval (paragraph → sentence) | **Chosen in the architecture, implemented, not yet wired** | Paragraph-level embedding for recall, sentence-level re-ranking for precision, avoiding pure-sentence noise and pure-paragraph imprecision. `Retriever.retrieve_with_sentences` implements it and has tests; the live Verify path calls paragraph-level `retrieve()`. No measurement yet says which is better — see Section 6 |

Both tables converged on the same two ideas from opposite directions: **decide structurally, and
abstain loudly.** The searching engine refuses to score its way to an answer; the Verify function
refuses to label its way out of a failure. Neither idea was copied from the other — they were
reached independently, which is the strongest sign they belong to the problem rather than to our
taste.

---

## 4. Prototype

### The searching engine, as built

1. **Read the reference as a query** — `reference_text.parse_reference_text` turns the raw entry
   into structured fields (title, authors, year, venue, DOI, arXiv id). The parser is deliberately
   conservative: it would rather return an empty field than a guessed one, because an empty field
   costs an abstention while a wrong field can select the wrong record.
2. **Ask the providers** — `openalex_lookup` then `crossref_lookup`, both keyless, both documented
   APIs; `metadata_lookup.lookup_reference` owns the chain order and stops at the first provider
   that settles the identity. Each provider gets exactly one request; a provider that raises is
   caught rather than trusted.
3. **Decide the identity** — `identity.select_identity` runs hard tiers (identifier → exact title →
   title-and-year-and-venue agreement) that either settle the identity or refuse to. Records that
   fail a tier are **reported in `rejected`**, not silently dropped, because the records a provider
   did return are part of the honest evidence.
4. **Report one of five states**, with every lookup attempt preserved: `VERIFIED`,
   `METADATA_MISMATCH`, `NEEDS_REVIEW`, `NOT_FOUND`, `LOOKUP_FAILED`.

### The Verify function, as built

1. **Resolve the source** — `SourceResolver` takes injected `locate` and `parse` callables, so the
   engine depends on neither the backend's paper store nor the parser package; the backend supplies
   both at the call site. That injection is what keeps the directory boundary real rather than
   aspirational.
2. **Index the passages** — `Retriever` over `faiss.IndexFlatIP` with L2-normalised
   `all-MiniLM-L6-v2` embeddings; cosine similarity over paragraph-level passages, local and free.
3. **Retrieve** — top-k passages by meaning, not by string, which is what makes paraphrase visible.
4. **Judge** — `Verifier.verify_with_retrieval` shows the model the claim and the retrieved
   passage(s) and asks for one of four labels. The model's only job is classification between two
   pieces of real text; it never writes a reference and never supplies the evidence. A reply that is
   not a valid label produces a `VerificationStatus`, not a verdict.

### What the prototype deliberately keeps separate

| Thing | Why it is a seam, not a hard-coded choice |
| --- | --- |
| The provider list | Injected into `lookup_reference`; ordering is a policy the backend sets ("most authoritative first"), so the chain can change without touching the decision rule |
| `locate` / `parse` | Injected into `SourceResolver`; storage-agnostic resolution is what lets the engine be tested without the backend's storage |
| The LLM client | Passed per call; the engine holds no client, no key and no default |

---

## 5. Test

Three layers, with different jobs: the bottom layer checks the rules, the middle replays recorded
reality, the top runs the real path.

### Layer 1 — component tests and invariants

The engine suite (352 tests) covers both subsystems, including the identity tiers, the provider
chain's failure handling, the reference parser, retrieval, and the verdict/status constructors. Two
invariants are asserted as pass/fail rather than as rates, because they are the design, not a
quality bar:

- `NOT_FOUND` implies **every** attempt completed and returned nothing, and there was at least one
  attempt.
- `LOOKUP_FAILED` implies **at least one** attempt did not complete.
- On the Verify side: a result with a non-`JUDGED` status must not carry a verdict — enforced in
  `VerificationResult.__post_init__`, not merely by convention.

### Layer 2 — recorded fixtures and sweeps

- The identity fixture harness replays recorded provider responses and sweeps thresholds: this is
  what pinned `YEAR_TOLERANCE = 1` from both sides instead of by intuition.
- The audit replay reproduces **36 of 39** bibliography cases and **3 of 3** PDF cases. Three cases
  are red and stay red: their fixtures no longer reproduce the mechanism their names claim. They are
  recorded for a human decision, not edited green.
- **The comparison measurement over 91 matched records** is the clearest single result in this
  document. Before the field-comparison change, the audit produced
  `0 VERIFIED / 0 MISMATCH / 91 NEEDS_REVIEW` — every reference to a human. That is *safe* and
  *useless*: a tool that reviews everything has not reviewed anything. After the change:
  `18 / 0 / 73`. The naive alternative (element-wise comparison with no recovered-value rule) would
  have produced `10 / 62 / 19` — **62 metadata-mismatch assertions the data does not support**,
  which is the false-accusation failure arriving through the front door. Author agreement: 69 of 91
  under the current gate, 36 of 91 under the comparison it replaced. The change landed in PR #44.

### Layer 3 — the real path

- **Verify acceptance** runs six labelled claims against a seeded excerpt of *Attention Is All You
  Need*, covering an overgeneralised claim, an unsupported causal claim and an incorrect GPU count.
  A case passes only if it returns HTTP 200, `COMPARED`, the expected verdict, the seeded source ID,
  **and** non-empty evidence with valid provenance. A returned judgement alone does not pass.
  The first live run — real DeepSeek calls, real embeddings, real FAISS retrieval through the
  Verify route — passed **12 of 12** across both thinking modes (6 cases × 2 modes; mean 1.373 s and
  1.262 s), with the harness's own stated limit: six smoke cases prove the wiring, not the accuracy.
- **Timing** is reported as a baseline with no pass/fail line: the audit N-curve medians are
  0.45 / 0.83 / 1.66 / 3.31 / 6.57 s for N = 5 / 10 / 20 / 40 / 80 — about 0.055 s per entry under
  injected latency, linear in N, which is the structural evidence that the batch path is serial by
  design and short-circuits correctly.

### Defects the tests and measurements found

| Defect | How it was found | Why it mattered |
| --- | --- | --- |
| An arXiv identifier read as a publication year (`1911.03587` → 1911) | Re-parsing the 140-reference corpus (fixed in PR #59) | **7 of 140 entries** took their year from an identifier — four displacing a real year on 2019/2020 papers, three supplying one for truncated entries that stated none. Because the identity rule rejects a record whose year disagrees by more than one, those references **could not resolve to the work they cite**: a parsing bug presenting itself as "the record is not there" |
| Everything routed to `NEEDS_REVIEW` (0/0/91) | The comparison measurement | Technically safe, practically worthless — a review queue with everything in it |
| A fuzzy matching tier that decided nothing | The threshold sweep | Deleted rather than tuned: an unmeasurable constant is a liability |

### Safety invariants, re-checked

The `LOOKUP_FAILED ≠ NOT_FOUND` rule is asserted on replay fixtures **and** on the real corpus: a
provider returning 500, a transport failure, and a 429 each produce `LOOKUP_FAILED` with the
corresponding error code, and the same rule is re-checked on the live 140-reference run, where it is
not a fixture assumption but an observed property of real throttling.

### What is not yet measured

The Verify accuracy bars were fixed **before** any data existed — Recall@5 ≥ 0.80, Recall@1 ≥ 0.50,
accuracy ≥ 0.80, F1 ≥ 0.85, Cohen's kappa ≥ 0.70 — which is the point: the target cannot move to
meet the result. The instrument is built (103 real claim–source pairs harvested onto a worksheet
with a retrieval escape hatch, so Recall@5 cannot be inflated by construction) and it is empty of
labels. **Engine accuracy on real claims is currently unmeasured**, and no number is reported here
in place of one.

---

## 6. Analysis

### What worked

1. **Measured constants instead of chosen ones.** `YEAR_TOLERANCE = 1` exists because 0 and 2 were
   both measured and both wrong. The fuzzy tier was deleted because the sweep showed nothing
   depended on it. The provider page size is 10 because the correct record for one real reference
   appeared at rank 9 — "relying on rank 1 is the same mistake as relying on a score threshold."
2. **Structural decisions where a copy cannot fake the answer.** The spoofed-record case is the
   clearest justification in the codebase for refusing to use a similarity score: the impersonation
   solves the text-similarity problem and cannot solve the venue-and-year problem.
3. **Failure as a first-class state — reached twice, independently.** The searching engine refuses
   to turn a failed lookup into "does not exist"; the Verify function refuses to turn "could not
   judge" into `NOT_FOUND`. The same rule was derived separately in two subsystems, from the same
   reasoning: **the dangerous output is the confident one.** Everything else in this document is a
   consequence of that sentence.
4. **Contracts that let four groups work in four directories.** The closed verdict enum is enforced
   by three components owned by two other groups; the injected `locate`/`parse` keeps the engine
   out of the backend's storage and the parser's package. The boundaries are load-bearing, not
   stylistic.

### What we would do differently

1. **The provider chain has no backoff.** Measured on the live corpus: a 140-reference run had 70
   requests answered and then took `429` until the next UTC midnight. The design note justified one
   request per provider "because neither API has a punitive backoff to wait out" — that was wrong at
   volume, and it is the first thing to fix.
2. **Query construction passes characters the provider rejects.** Five of the 140 corpus queries
   returned HTTP 400 because punctuation (`?`, `,`, `:`) went into the title-search query. Found by
   running real data — not by any test — which is the reminder that fixtures encode our assumptions.
3. **A red test whose fixture cannot fail is worse than a missing test.** The three red forged-
   record cases are still unresolved: the fixture mechanism does not reproduce what the case name
   claims. They are recorded rather than edited, but leaving them red indefinitely erodes the
   signal.
4. **Deliberate duplication is still duplication.** `title_matching.py` mirrors the backend's title
   normalisation with two documented differences. The duplication is intentional (the engine may
   not import the backend) but it can drift silently, and nothing currently detects the drift.

### Where the design goes next

| Open item | State | Owner |
| --- | --- | --- |
| Verify accuracy against the pre-committed bars | Instrument built; 103 pairs awaiting human labels | Engine + human annotators |
| Two-stage retrieval (paragraph → sentence) | Decision recorded, implementation exists and is tested, live path still paragraph-level | Engine |
| 429 backoff / retry in the provider chain | Not built; measured as a real limit | Engine |
| HTTP 400 from punctuation in search queries | Reproduced on 5 corpus references; not fixed | Engine |
| Three red forged-record fixtures | Awaiting a human decision | Engine |
| Real-user validation of the personas | Planned and documented; not run | Whole team |

### Takeaway

The two subsystems look different — one queries public APIs about a reference, the other runs a
language model over retrieved text — but they were designed against the same constraint from
opposite ends: **a tool that checks other people's accuracy must be honest about its own limits.**
The searching engine can say "we could not complete the search"; the Verify function can say "the
model did not judge this". Both answers are less satisfying than a confident verdict, and both are
the reason the confident verdicts can be trusted.

---

## Additional Notes — evidence index

Every design claim in this document is traceable to a merged pull request. The PR numbers below were
read from the repository's merged pull requests on 15 October 2026; each names the PR that
introduced or established the evidence, not merely the last one to touch the file. The document
itself was delivered as **pull request #62** (`engine/design-thinking-searching-and-verify`).

| Claim in this document | Where to check it | Backing PR |
| --- | --- | --- |
| Five-state audit contract; `not_found` requires every attempt to be `not_found` | `docs/audit-contract.md`; `engine/engine/metadata_lookup.py` (module docstring) | #38, #41 |
| Structural identity rule; `YEAR_TOLERANCE = 1`; the removed fuzzy tier | `engine/engine/identity.py` (module docstring); `docs/audit-contract.md` §identity | #38 |
| Provider chain: OpenAlex first, Crossref fallback, one request each | `engine/engine/metadata_lookup.py`; `backend/src/services/provider_chain_lookup.py` | #41 |
| The 91-record comparison measurement (0/0/91 → 18/0/73; naive 10/62/19) | `docs/audit-contract.md` §5, measured 2026-09-19 | #44 |
| Closed verdict set and its three consumers; status vs verdict | `engine/engine/verifier.py` (module and enum docstrings) | #28 (engine), #43 (backend) |
| arXiv-year defect: 7 of 140 entries, four displacing a real year | commit `b45f59e` (`fix(engine): stop reading an arXiv identifier as the year`) | #59 |
| Two-stage retrieval decision | `docs/architecture.md` §5.3; `Retriever.retrieve_with_sentences` | #12 (architecture record) |
| Verify acceptance: six labelled cases, pass conditions, and the limits of a smoke run | `docs/verify-acceptance.md` | #61, #60 (provider matrix) |
| Live DeepSeek run: 12 passed / 0 failed, per-case results, timings | `docs/verify-acceptance-deepseek-live.md` (2026-10-11) | #61 |
| Audit timing baseline (N-curve medians, ~0.055 s/entry) | `docs/accuracy-baseline/audit_timing.json` | #57 |
| OpenAlex 429 after ~70 requests; live-run note | `docs/team.md` §3 | #58 |
| Audit replay 36/39 + 3/3; the three red cases | `docs/team.md`; `docs/audit-live-acceptance/` | #47 |
| Verify bars and the 103-pair worksheet | `engine/tests/benchmarks/CLAIM_PASSAGES.md`; `docs/team.md` §2 (criteria 4–5) | #39, #57 |
| Manual source-PDF selection for Verify (with the ambiguity path) | `docs/verify-acceptance.md` scope note; backend verify routes | #48 |
| Personas synthesised; interviews not run | `docs/team.md` §2 (criterion 1); `docs/user-research/` | #12 (added), #45 (consolidated) |
