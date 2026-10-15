# ClaimTrace — Project Idea

**Group 18 · 41129 Software Innovation Studio · UTS · 15 October 2026**

ClaimTrace checks whether a paper's citations actually support the claims they are attached to: a
Chrome extension that works inside Overleaf, and a web dashboard that checks a whole reference list
at once. It answers one question — *does the cited source say what this sentence claims it says?* —
and shows the evidence behind every answer.

---

## 1. Background Research

### How this research was done

Three inputs, in order of weight: the peer-reviewed literature on citation accuracy and on what peer
review actually catches; a teardown of thirteen products that touch references in some way; and the
team's own experience — all seven of us write papers and have hit the moment this project is about.
A structured interview round with five researchers outside the team is planned and documented
(protocol, recruiting channels, output format); it has not been run yet, which is why Section 3
treats the personas as hypotheses rather than findings.

One rule was applied to every number below, after our own first pitch failed to meet it:
**quote a report, its scope and its growth rate — or quote nothing.**

### Finding 1 — citations frequently do not say what authors think they say

| Measure | Value | Source |
| --- | --- | --- |
| Quotations incorrect | **16.9%** (95% CI 14.1–20.0) | Baethge & Jergas 2025, *Research Integrity and Peer Review* 10(1):13 |
| Of which major errors | **8.0%** (95% CI 6.4–10.0) | same |
| Evidence base | **46 studies, ~32,074 quotations** | same |
| Trend over forty years | flat — meta-regression slope −0.002, **p = 0.85** | same |

The earlier pooled estimate (Jergas & Baethge 2015: 25.4% total, 11.9% major) points the same way,
and field-level studies range widely — 41% citation errors in dermatology, 16% in anaesthesiology,
7.6% mean quotation inaccuracy in orthopaedics. This is not one bad field. **One in six quotations
is wrong, half of those errors are serious, and it has not improved in forty years.**

### Finding 2 — the checking that should catch it does not happen

- Reviewers failed to identify **two-thirds of major errors** in a fictitious-manuscript experiment
  (Baxt et al. 1998, *Ann Emerg Med*, n = 203).
- Reviewers found a mean of **3 of 9** deliberately planted errors across 607 *BMJ* reviewers, and
  training barely helped (Schroter et al. 2008, *J R Soc Med*).
- A *BMJ* 2023 analysis states that responsibility for auditing cited literature "**rests with those
  who selected it, not reviewers**" and proposes **AI tools integrated into submission portals to
  confirm cited works exist and flag likely mis-citations** (*BMJ* 2023;383:e076441).

That last point is, in effect, this project's value proposition already published in a medical
journal. The reason it does not happen is cost: checking one citation by hand means finding the
source PDF, searching it, and reading around the hit — minutes per citation, hours per paper, which
is exactly the work that gets skipped at 2 a.m. before a deadline.

### Finding 3 — retracted and fabricated work keeps being cited

- Across independent samples spanning 1990–2026, roughly **70–94% of retracted papers continue to
  be cited** after retraction, usually neutrally or positively, and only 4–18% of citing articles
  mention the retraction.
- **93.9%** of 994 retracted Nature Index articles kept receiving citations — 21,047 post-retraction
  citations, **39.8% of them positive** (*J Inf Sci* 2026).
- The retracted Wakefield paper has been cited **1,154 times after retraction versus 643 before** —
  it is cited *more* after retraction than before.
- The data to detect this is free: Crossref acquired the Retraction Watch database and released it
  CC0 in September 2023 (~43,000 records, plus Crossref's own ~14,000).

### Finding 4 — AI writing tools made the problem acute, and dated it

- Fabricated citations rose **more than twelvefold** in the samples tracked: 1 in 2,828 papers
  (2023) → 1 in 458 (2025) → about **1 in 277** in the first seven weeks of 2026, from an audit of
  2.47M PMC articles and 125.6M references. **98.4% of affected papers saw no publisher action**
  (*Lancet* 2026).
- GPT-4o produced wholly fabricated references in **19.9%** of cases, and **45.4%** of the real ones
  contained bibliographic errors — nearly two-thirds defective (*JMIR Mental Health* 2025; n = 176).
- GPT-3.5 fabricated **55%** of references and erred in **43%** of the genuine ones (*Sci Rep* 2023).

Five years ago the problem was chronic. Today it is compounding annually, and the tools researchers
actually use to write are among its causes.

### What the research says is missing

Every existing tool checks something — the record's metadata, the text's similarity, how *other*
papers cited a work. **Nothing in a researcher's workflow checks the sentence against its source**,
and doing it by hand is expensive enough that it is skipped. That is the gap this project addresses.

---

## 2. Project Scope

### What the project delivers

Three surfaces, one engine:

| Surface | What it does |
| --- | --- |
| **Batch audit** (web dashboard) | Checks a manuscript's reference list against real publication records — OpenAlex first, Crossref as fallback, both keyless — and reports every reference in one of five states: verified, metadata mismatch, needs review, not found, or lookup failed |
| **Verify** (web dashboard) | Compares a selected claim with the source it cites: retrieves the relevant passage from the cited paper and classifies the relationship — supported, partially supported, contradicted, not found — always showing the passage it decided on |
| **Overleaf hover** (Chrome extension) | Shows the citation in place: hover a `\cite{}` and see the citation, its bibliography entry and its location, marked not checked — the extension runs the bibliography audit, and the passage-level check is the dashboard's Verify |

### In scope

- Checking a bibliography against external publication records (existence and field-level agreement)
- Checking a sentence against the source it cites, with the evidence shown
- Working inside the editor at the moment of writing, and batch-checking before submission
- Running entirely with the researcher's own AI provider credentials, across 17 supported providers

### Out of scope

| Not built, deliberately | Why |
| --- | --- |
| Reference management, formatting, bibliography styles | Zotero and Mendeley do this well; it is not the problem |
| Text-similarity and plagiarism checking | Turnitin and iThenticate own this; it answers a different question |
| Generating or rewriting the researcher's text | The product checks claims; it does not make them |
| Judging authors or declaring misconduct | It reports what the record says and shows the evidence |
| Retaining manuscripts or credentials | Papers are processed transiently; keys live only for the request |
| Exportable reports, shared team libraries, a reviewer workspace | Deferred (P2 in the user stories) — valuable, but not on the critical path to a trustworthy core |

### Boundaries that are product rules, not features

Two rules constrain the scope more than any feature list, and both make the product *less*
conclusive on purpose:

1. **A failed check is never reported as a negative finding.** `NOT_FOUND` means the search
   completed and found nothing; `LOOKUP_FAILED` means the search could not run, and is reported as
   *not checked*. The audit never converts the second into the first, because the most damaging
   output this class of tool can produce is not a wrong answer — it is a reassuring one.
2. **No result without its evidence.** Every verdict ships with the passage, page and similarity it
   was based on, so the researcher can overrule the tool rather than trust it blindly.

The project is a working prototype on this scope: the extension (v0.4.0), the dashboard, the API,
and the engine all exist and pass their test suites, and the end-to-end flow has been accepted on
the real Overleaf with a real backend.

---

## 3. Target User

Three user types, defined as personas in `docs/user-research/personas.md` and prioritised as
primary, secondary and long-term.

### Primary — the anxious first author

A PhD student or early-career researcher writing a conference paper in Overleaf, responsible for
integrating sections written by several co-authors. They do not fully trust citations they did not
write, and have no time to check them by hand. Their deadline scenario is concrete: 48 hours out,
thirty-plus unverified citations in the Related Work, and — in their words — "can only let most of
them slide on gut feel." They asked for two things: hover in the editor and know whether a citation
is right, and batch-check the whole paper to find the few citations that most need human review.
They are the wedge user: the pain is sharpest, and the fix has to be instant and non-disruptive.

### Secondary — the supervising PI

An academic supervising five or more students, gating every draft in fragmented time. They cannot
verify each citation themselves, they have seen references pasted from ChatGPT, and they want
evidence rather than conclusions so their feedback can be specific. Their scenario: an eight-page
draft and thirty minutes. They asked for a risk-ranked report with doubtful citations marked and
source evidence attached. They are the natural paying user — a lab or department subscription — and
the batch audit is designed for them.

### Long-term — the reviewer

A conference reviewer reading five to ten submissions a year, who suspects a claim over-interprets
its source but cannot afford the time to verify it, and needs specific, citable evidence for the
review. They asked to see the claim and the cited passage side by side. They are not a
direct-payment user; this is a publisher-facing direction, not a current feature.

### Who this is not for

People who want references generated or formatted; authors who never cite; and institutional
metadata clean-up work, which is adjacent (the audit data helps) but not the user this product is
designed around.

### An honest note on method

These personas are **synthesised** — from the literature above and from the team's own experience
as researchers. The interview round that would validate them (five researchers who recently
submitted to a top venue) is planned and documented but not yet run. The shared insight that came
out of the synthesis — all three types want to see the source evidence, not an AI conclusion — is
already load-bearing in the design, and is the first hypothesis the interviews will test.

---

## 4. Solutions

### 1. Verify a claim against its source

Select a sentence in the dashboard, or submit it directly; the system finds the cited paper, retrieves
the passage in it that bears on the claim, and classifies the relationship: **Supported**,
**Partially supported**, **Contradicted**, or **Not found**. "Partially supported" exists to name the
most common real-world failure — overstating what a source says, or dropping a qualifier. The
retrieved passage is always displayed, so the researcher judges the judgement.

### 2. Hover in Overleaf

The extension turns a citation into something you can read in place: hover the `\cite{}` and the
card shows the citation, its bibliography entry and its location in the editor. It passes no
judgement on the claim — the extension runs the bibliography audit, not the claim comparison — so
the card states **not checked**, and the passage-with-verdict view belongs to the dashboard's
Verify. A build that did show the retrieved source passage in the card shipped on 18 September 2026
and was disabled the next day, when the extension was made audit-only. The card is built from local
data — no network request and no spinner on hover — because the moment it interrupts the writing
flow, it has failed at the thing it was built for.

### 3. Audit a whole bibliography

Paste or upload a reference list (or let the extension read the `.bib` from Overleaf) and every entry
is checked against real publication records — **OpenAlex first, Crossref as fallback, both
keyless** — and reported in one of five states, with a detail panel per reference showing the
field-by-field checks and every lookup attempt made. This is the feature for the supervisor's
thirty minutes: a risk-ranked list of what needs human eyes, instead of a whole paper.

### 4. Cross-check a `.bib` against the source PDFs

For a bibliography whose sources the researcher already has, the system compares each entry's
title, year, authors, venue and DOI against the PDF — catching wrong years, garbled titles and DOIs
pointing at the wrong paper, with no network calls at all.

### 5. Trust built into the output

Under all four solutions:

- **Evidence, not verdicts** — every result carries the passage or the record it came from.
- **The failure rule** — an inconclusive check is reported as inconclusive, never as a negative
  finding.
- **A constrained model** — the AI's only job is to classify the relationship between two passages
  the system has already retrieved from real text; it never writes a reference, and if it is
  unavailable the result is an explicit failure state, never a guessed verdict.
- **The researcher's own credentials** — 17 supported providers, keys held only for the lifetime of
  the request; the product holds no shared key and stores no key.

**Built with:** FastAPI backend, React dashboard, Chrome MV3 extension, and a Python engine
(sentence embeddings with a local FAISS index for retrieval; a provider chain and an identity rule
for the audit). The system runs as a working prototype today, with the end-to-end flow accepted on
the real Overleaf.

---

## 5. Target Market

### Demand

**5.7 million** articles, reviews and conference papers were published in 2024, up from 3.9 million
five years earlier — **+46%**, about 7.9% a year (Dimensions data reported by STM and Research
Consulting, January 2026). Every one of those papers carries citations, and Findings 1–4 say a
measurable fraction of them are wrong and going unchecked.

### The money, and the honest problem with it

The natural market to quote — reference-management software — is sized **three times apart by three
commercial vendors** for the same year: $371M, $385M and $1,150M for 2024. None of those estimates
is audited, and we cannot defend a point estimate, so we do not.

What an auditor can check is Clarivate's **Academia & Government** segment — the part of the
company containing Web of Science and EndNote — at **$1,266.0M in FY2025**, filed with the SEC on
Form 10-K. For scale, the scholarly publishing market itself is roughly $27B at a 1.3% CAGR
(Outsell) — the corpus grows far faster than the revenue that pays for it.

### The hole in the price list

What is actually purchasable today, and what each price buys:

| Vendor | Price | What it actually checks |
| --- | --- | --- |
| iThenticate (direct) | **$125** / manuscript ≤ 25,000 words | text similarity only |
| EditVerse | **$175** / manuscript | reference metadata and existence |
| Enago | **$18** | reference formatting |
| Crossref Similarity Check | $0.75 / document | similarity matching |
| Harbin Institute of Technology Library | CNY 10 / citation | confirms a paper exists and is indexed |

Every published price buys **formatting, metadata verification, or text-similarity matching**. None
buys claim-support verification. **The hole in the price list is the product.**

### Willingness to pay is demonstrated, not assumed

scite.ai — the closest funded neighbour — reached **~21,000 paying subscribers** and **$3.6M
annualised subscription revenue** before being acquired by Research Solutions (NASDAQ: RSSS) at
roughly **$29M all-in** (≈$21.1M initial consideration plus a $15.4M earn-out finalised July 2025).
Its consumer pricing is $20/month Basic and $50/month Pro, billed yearly. People and institutions
pay for citation intelligence; they currently pay for a *different question* (Section 6).

### Segments and route to market

1. **Individual researchers** — free tier for single checks; subscription for batch audit and
   unlimited verification (the scite-comparable entry point).
2. **Labs and supervisors** — departmental subscriptions, the batch audit with reports for students
   (the PI persona, and the most natural first paid tier).
3. **Institutions** — research-integrity offices and libraries; the audit output is exactly the
   evidence they currently assemble by hand.
4. **Publishers** — the *BMJ* 2023 proposal of citation checks integrated into submission portals is
   a publisher-facing product, not a researcher tool; a direction, not a current plan.

---

## 6. Competitors in the current market

### The four classes of incumbent

| Class | Examples | What they actually check | Why the gap survives |
| --- | --- | --- | --- |
| Reference managers | Zotero (14.4M users in 2024, +25% YoY), Mendeley, EndNote | Store and format metadata | They never read the cited paper |
| Similarity checkers | Turnitin, iThenticate | Strings of five or more words matching a database | A claim reworded in the author's own voice matches no string — so a mis-cited claim contributes nothing to the score. iThenticate's own guide lists "information or language attributed to the wrong source" among what it does not identify |
| Reference checkers | ReciteWorks, Edifix, CiteTrue, Paperpile, SciSpace | Whether the record exists | Asked directly whether it checks that quoted text appears in the cited source, ReciteWorks' own FAQ answers "No, not currently" |
| Citation-intent platforms | scite.ai, Semantic Scholar | How *other people* cited a paper | The unit of analysis is the cited paper, not your sentence; Semantic Scholar's intent is purpose, not stance, and only ~12% of citations carried any intent in a live API test |

### The real alternative is the status quo

For most researchers the competitor is not a product: it is Ctrl+F and a downloaded PDF, or asking
a chatbot — which, per Finding 4, is itself a cause of the problem. Both alternatives are the thing
this project replaces.

### The closest competitor: scite.ai

scite is the one a reviewer names first, and it is worth studying because it proves the category:
founded 2018, acquired by a NASDAQ-listed company in 2023, with 1.6B+ Smart Citations. It labels how
a paper has been cited — supporting, contrasting or mentioning — and its Reference Check accepts a
manuscript and reports, per reference, retractions and editorial notices.

Two things about it matter here:

- **It answers a different question.** scite tells you reference #12 has been retracted, or how
  forty papers used it. It cannot tell you that *your sentence about #12 is wrong* — and to its
  credit, it does not claim to.
- **Its hardest classes are weak, by its own measurements.** Its published F-scores are 96.3 for
  "mentioning" but 55.3 for "supporting" and 20.5 for "disputing"; it states it fails to identify
  about **30%** of citation statements in PDFs; and an independent 2023 audit of citations to
  retracted works found human assessors labelling 17 contrasting citations where scite showed none.
  (scite-affiliated authors dispute that audit's method; the dispute is unresolved.) These are
  precisely the two classes this project's Verify exists to handle.

### The column is unoccupied, not empty

Prototypes and small entrants are attempting claim-support checking — RefVerifier (71% end-to-end
accuracy, September 2026), Grounded AI, sci2sci (€1.2M pre-seed), plus RefCheckAI, CiteVahti,
CiteGuard and a university library service. Claiming nobody is trying would be false. Claiming no
*established* product owns this is defensible and checkable.

### ClaimTrace's position

| Question | Zotero | Turnitin | scite | ClaimTrace |
| --- | --- | --- | --- | --- |
| Does the reference exist? | stores it | — | yes | yes (Audit) |
| Is its metadata right? | — | — | partial | yes (Audit) |
| How have others cited it? | — | — | yes | no, deliberately |
| **Does YOUR source support YOUR sentence?** | — | — | — | **yes (Verify)** |

Two layers — **Audit** the record, **Verify** the meaning — plus the failure rule that no competitor
documents: a failed lookup stays a failed lookup, and is never converted into a verdict that a
reference does not exist. In one line: **every tool on the market checks the paper; none checks the
sentence.**

---

## Sources

The full source list, with each figure's scope and origin, is in `ClaimTrace-Market-Analysis.md`
(§8). Statistical claims above cite: Baethge & Jergas 2025 · Jergas & Baethge 2015 · Baxt et al.
1998 · Schroter et al. 2008 · *BMJ* 2023;383:e076441 · *J Inf Sci* 2026 · Retraction Watch and
Crossref (September 2023) · *Lancet* 2026 · *JMIR Ment Health* 2025;12:e80371 · Walters & Wilder
2023 · STM & Research Consulting (January 2026) · Clarivate SEC Form 10-K FY2025 · Outsell via STM
Global Brief 2021 · Corporation for Digital Scholarship Annual Report 2024 · scite.ai and Research
Solutions filings · Nicholson et al. 2021 · Bakker, Theis-Mahon & Brown 2023 · Turnitin and
iThenticate documentation · ReciteWorks FAQ · arXiv 2609.07652.
