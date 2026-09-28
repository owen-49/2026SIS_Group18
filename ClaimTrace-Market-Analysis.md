# ClaimTrace — Market & Competitor Analysis

**Group 18 · 41129 Software Innovation Studio · 22 October 2026**

Companion to `ClaimTrace-Market-Competitor-Analysis.pptx`. Every figure in both documents was
re-checked on **24 September 2026** and carries its source inline. Where a number could not be
traced, it was removed rather than estimated.

---

## 1. Method, and why it matters here

The A1 pitch circulated a set of market numbers that did not survive checking. This analysis
replaces them. The rule applied throughout:

> **Quote a report, its scope and its CAGR — or quote nothing.**

Two consequences run through everything below:

- **Scope is stated every time.** "The reference-management software market" and "the scholarly
  publishing market" differ by two orders of magnitude. A number without its scope is not evidence.
- **A vendor's self-published figure is labelled as such.** Turnitin's, Overleaf's and scite's own
  claims are used — but attributed to them, and never presented as audited fact.

Where sources conflict, the conflict is reported rather than resolved by picking the flattering
number.

---

## 2. The problem: citations do not say what authors think they say

### 2.1 The headline

**One in six quotations is wrong, and half of those errors are major — with no improvement in
forty years.**

| Measure | Value | Source |
|---|---|---|
| Quotations incorrect | **16.9%** (95% CI 14.1–20.0) | Baethge & Jergas 2025, *Research Integrity and Peer Review* 10(1):13 |
| Of which major | **8.0%** (95% CI 6.4–10.0) | same |
| Studies pooled / quotations examined | **46 studies, ~32,074 quotations** | same |
| Trend over time | meta-regression slope −0.002, **p = 0.85** — flat | same |

The earlier pooled estimate (Jergas & Baethge 2015, *PeerJ* 3:e1364) gives 25.4% total / 11.9%
major across 28 studies. The 2025 paper supersedes it with a larger sample; both point the same way.
Field-level studies range widely — 41% citation errors in dermatology (George & Robbins 1994),
16% in anaesthesiology (Lukic et al. 2026), 7.6% mean quotation inaccuracy in orthopaedics
(Buijze et al. 2012) — so this is not one bad field.

### 2.2 Nobody downstream is catching it

- Reviewers failed to identify **two-thirds of major errors** in a fictitious-manuscript experiment
  (Baxt et al., *Ann Emerg Med* 1998, n = 203).
- Reviewers found a mean of **3 of 9** deliberately planted errors across 607 *BMJ* reviewers;
  training barely helped (Schroter et al., *J R Soc Med* 2008).
- A *BMJ* 2023 analysis states responsibility for auditing cited literature "**rests with those who
  selected it, not reviewers**", notes peer review "may sometimes encourage mis-citation", and
  proposes **AI tools integrated into submission portals to confirm cited works exist and flag
  likely mis-citations** (*BMJ* 2023;383:e076441).

That last item is, in effect, ClaimTrace's value proposition already published in a medical journal.
It is the single most useful citation the project has.

### 2.3 Retracted work keeps being cited

Across independent samples spanning 1990–2026, **roughly 70–94% of retracted papers continue to be
cited after retraction**, most citations neutral or positive, and typically only **4–18% of citing
articles mention the retraction**.

- **93.9%** of 994 retracted Nature Index articles kept receiving citations — 21,047 post-retraction
  citations, **39.79% of them positive** (*J Inf Sci* 2026).
- The retracted Wakefield autism paper has been cited **1,154 times after retraction vs 643 before**
  — it is cited *more* after retraction than before (Retraction Watch Leaderboard).
- **52.5%** of the 200 most recent citing articles inappropriately cited the retracted Surgisphere
  COVID papers (*Science*, Jan 2021).

The infrastructure to detect this is free: on **12 September 2023 Crossref acquired the Retraction
Watch database and released it CC0** (~43,000 records, plus Crossref's own ~14,000).

### 2.4 AI has made it acute and dated

- Fabricated citations rose **more than 12-fold**: 1 in 2,828 papers (2023) → 1 in 458 (2025) →
  about **1 in 277** in the first seven weeks of 2026 — from 2,471,758 PMC articles and 125.6M
  references audited. **98.4% of affected papers saw no publisher action** (*Lancet* 2026).
- GPT-4o produced wholly fabricated references in **19.9%** of cases, and **45.4%** of the real ones
  contained bibliographic errors — nearly two-thirds defective (*JMIR Mental Health* 2025;12:e80371;
  n = 176, so treat the exact rate as indicative).
- GPT-3.5 fabricated **55%** of references and erred in **43%** of the genuine ones (Walters &
  Wilder, *Sci Rep* 2023; 636 citations).

This is the demand driver, and it has a date on it. Five years ago the problem was chronic; today it
is compounding annually.

---

## 3. Market size: growing demand, a small and badly-measured tooling market

### 3.1 Demand

**5.7 million** articles, reviews and conference papers were published in **2024**, up from
**3.9 million** five years earlier — **+46%**, roughly 7.9% a year (Dimensions data reported by STM
and Research Consulting, 13 January 2026).

For contrast on the money side: the global scholarly publishing market was **$27B → $28B → $26.5B**
in 2018 → 2019 → 2020, forecast to return to ~$28B by 2023, a **1.3% CAGR** (Outsell, in STM Global
Brief 2021). The corpus grows much faster than the revenue that pays for it.

### 3.2 The tooling market — and the honest problem with it

Vendors sizing the **reference-management software** category disagree by a factor of three:

| Source | Scope | 2024 estimate |
|---|---|---|
| Global Info Research | reference-management software | **$371M** |
| YH Research | reference-management software | **$385M** |
| WiseGuyReports | reference-management software | **$1,150M** |

Same category, same year, **3× apart**. All three are commercial estimates whose stated scope
differs; none is audited.

**The one number an auditor has seen** is Clarivate's *Academia & Government* segment — which
contains Web of Science and EndNote — at **$1,266.0M** in FY2025 (FY2024 $1,326.4M; FY2023
$1,323.3M; adjusted EBITDA $548.0M), filed with the SEC on Form 10-K.

**Why this is the honest slide:** the temptation is to quote $619M-by-2032 or a 7.6% CAGR because it
sounds like a market. We cannot defend the point estimate, so we show the spread and quote the
audited segment instead. A tutor who checks will find the same disagreement.

### 3.3 The gap in the price list

Nobody sells the thing ClaimTrace does. What is actually purchasable today:

| Vendor | Price | What it actually checks |
|---|---|---|
| iThenticate (direct) | **$125** / manuscript ≤25,000 words | text similarity only |
| EditVerse | **$175** / manuscript | reference list verification — metadata and existence |
| Enago | **$18** | reference formatting |
| Crossref Similarity Check | $0.75 / document (first 100 free) | similarity matching |
| Harbin Institute of Technology Library | CNY 10 / citation | confirms a paper exists and is indexed |

Every published price buys **formatting, metadata verification, or text-similarity matching**. None
buys claim-support verification. **The hole in the price list is the product.**

---

## 4. Competitive landscape

### 4.1 The four classes of incumbent

**① Reference managers — Zotero, Mendeley, EndNote.**
Store and format metadata. Zotero alone has **14.4M users** in 2024, up 25% year on year
(Corporation for Digital Scholarship Annual Report 2024). They do not read the cited paper.

**② Similarity checkers — Turnitin, iThenticate.**
Match text; in the vendors' own words they do nothing more:

- Turnitin help centre: "**Turnitin does not check for plagiarism.** … The percentage … defines how
  much of that material matches other material in the database."
- iThenticate user guide: "**its primary function is to highlight matching content from other
  sources** … a low score does not guarantee the absence of plagiarism."
- A US Naval Postgraduate School guide lists what iThenticate does *not* identify, including
  "**information or language attributed to the wrong source**", and notes "the source that
  iThenticate identifies is **not necessarily the source the writer used**."

The mechanical reason a paraphrased-but-unsupported claim is invisible: the score is flagged on
**strings of five words or more** matching the database. A claim reworded in the author's own voice
that contradicts its source matches no string anywhere, contributes nothing to the score, and never
appears in the report.

**③ Reference checkers — ReciteWorks, Edifix, CiteTrue, Paperpile, SciSpace.**
Confirm the record exists. Asked directly whether it checks that quoted text appears in the cited
source, **ReciteWorks' own FAQ answers "No, not currently."**

**④ Citation-intent platforms — scite.ai, Semantic Scholar.**
Classify how *other people* cited a paper. Semantic Scholar's citation intent is *purpose*
(background/method/result), not *stance*, and in a live API test only ~12% of citations carried any
intent at all. scite is the strongest of the four and is analysed in §5.

### 4.2 The matrix

`fig/gap_matrix.png` on slide 3 plots thirteen products against four questions. The first three
columns are occupied by established products. **The fourth — does YOUR source support YOUR
sentence — is owned by no established product.**

Two honest qualifications, both of which strengthen rather than weaken the argument:

- **The column is unoccupied, not empty.** Prototypes and small vendors are attempting it:
  RefVerifier (**71% end-to-end accuracy**, arXiv 2609.07652, September 2026), Grounded AI, sci2sci
  (€1.2M pre-seed, September 2026), plus RefCheckAI, CiteVahti, CiteGuard and a University of
  Pittsburgh HSLS service. Claiming nobody is trying would be false; claiming no *established*
  product owns it is defensible and checkable.
- **"Partial" marks are deliberate.** Paperpal claims a citation-relevance check with no independent
  evaluation; Grounded AI and sci2sci have adjacent capabilities. The matrix distinguishes
  "documents this" from "claims this".

---

## 5. Case study: scite.ai

Chosen because it is the biggest competitor, the one a reviewer names first, and the only one with a
comparable data pipeline.

### 5.1 What it is

- Founded 2018 in Brooklyn; co-founder & CEO Josh Nicholson.
- **Smart Citations** label how a paper has been cited — supporting, contrasting or mentioning —
  one label per citation statement. **1.6B+** Smart Citations, **317M+** articles indexed,
  **44+** publisher partners.
- Acquired by **Research Solutions (NASDAQ: RSSS)**, announced 27 November 2023, closed 1 December
  2023. **Be precise if asked:** ≈$21.1M initial consideration per the FY2025 10-K, earn-out
  finalised at **$15.4M in July 2025** — all-in roughly **$29M**. The commonly-quoted "$20.9M" is
  the initial figure net of cash acquired, not the total.
- At acquisition: **~21,000 paying B2C subscribers**, **$3.6M** annualised subscription revenue,
  **$1.1M** FY2023 revenue.

### 5.2 Why it is the case to study

It proves the category is real and funded — a NASDAQ-listed company bought it. It publishes its
methods. And it answers a **different question**: "how have others cited this paper?", never "does
my sentence match my source?"

### 5.3 Its accuracy, from its own paper

Nicholson et al. (2021), *Quantitative Science Studies* 2(3):882–898, doi:10.1162/qss_a_00146:

| Measure | Value |
|---|---|
| F-score, mentioning | 96.3 |
| F-score, supporting | **55.3** |
| F-score, disputing | **20.5** |
| Disputing, later | 58.97 F at 85.19 precision |
| Real-world distribution | ~92.6% mentioning, 6.5% supporting, **0.8% disputing** |
| Ingestion (their own stated limit) | "fails to identify approximately **30%** of citation statements/references in PDF files" |

The classes that carry the scientific signal are the rarest, and the hardest to classify.

### 5.4 An independent audit found worse

Bakker, Theis-Mahon & Brown (2023), *Hypothesis* 35(2), doi:10.18060/26528 examined 324 citations of
retracted works. scite classified 98 of them (no full text available for 118):

| | supporting | mentioning | contrasting |
|---|---|---|---|
| **scite** | 2 | 96 | **0** |
| **Human assessors** | 42 | 39 | **17** |

F-measures ranged **0.0–0.58**. Human assessors found **17 contrasting citations where the product
showed none** — in a study of *retracted* papers, the one context where a contrasting signal matters
most.

*If asked:* scite-affiliated authors published a reply in 2025 disputing the method. Acknowledge it
and note the dispute is unresolved; do not present the critique as settled.

### 5.5 Function 2: Reference Check

scite's second relevant feature accepts a manuscript PDF and reports, per reference, how it has been
cited by others — retractions, editorial notices, contrasting findings. Pricing (scite.ai/pricing):
$20/mo Basic, $50/mo Pro, both billed yearly; no institutional price published.

**Where it stops:** the unit of analysis is still the cited paper, and the evidence is still what
third parties did with it. It tells you reference #12 has been retracted. It **cannot** tell you that
your sentence about #12 is wrong — and to its credit, it does not claim to. There is also **no
published accuracy figure** for Reference Check; Smart Citations has a peer-reviewed evaluation and
this feature does not.

---

## 6. ClaimTrace's position

Two layers, and a rule about failure.

**Audit — the record.** Does the reference exist, and do title, authors, year and venue agree?
OpenAlex first, Crossref as fallback, both keyless.

**Verify — the meaning.** Does the cited source actually support the sentence it is attached to?
The supporting or contradicting passage is **shown**, not reduced to a label.

**The failure rule — the genuinely unique part.** A failed lookup stays `LOOKUP_FAILED`.
`NOT_FOUND` means the search *completed* and found nothing; it is never converted into a claim that
a reference was fabricated (`claimtrace/docs/audit-contract.md` §2, §4). No competitor documents
this distinction. It matters because the most damaging output this class of tool can produce is not
a wrong label — it is a **reassuring** one. A product that turns a timeout into "looks fabricated",
or an ingestion miss into a clean bill of health, is worse than no product.

This is also why the honest framing of the competitive position is: **no established product owns
this column**, not "nobody is trying".

---

## 7. What changed from the A1 pitch, and why

Four figures in the A1 deck should not be repeated. Replacing them is the main analytical output of
this exercise.

| A1 pitch said | Problem | Now |
|---|---|---|
| "12,402 papers, 7.1%" | **Fused citation.** 12,402/7.1% comes from an unrefereed vendor blog analysis (June 2026, 54 biomedical journals, severity subset only 1.4%); the adjacent "375 retracted / 76%" is a UFPE doctoral thesis on Latin American retractions 2002–2022. The "9,662" appears in **neither**. | 16.9% / 8.0% across 46 studies and 32,074 quotations (Baethge & Jergas 2025) |
| "Reference-management market $371M → $617M, 7.6% CAGR" | Traceable to a commercial vendor, but other vendors size the same market **3× higher**. Not defensible as a point estimate. | Vendors shown 3× apart ($371M–$1,150M) + Clarivate's audited $1,266.0M SEC figure |
| "GhostCite: 76.7% of reviewers…" presented as a survey | Not a survey. arXiv:2602.06718 (preprint) plus an IEEE S&P 2026 **poster**; 76.7% is roughly 25 of 32 reviewers within a 94-respondent AI/security subset. | Removed. The *BMJ* 2023 analysis and the reviewer-error experiments carry the point with better evidence |
| "scite acquired for $20.9M, 2M+ users" | $20.9M is the **initial** consideration net of cash; the earn-out took it to ≈$29M. | ≈$29M all-in, with the breakdown given if asked |
| "Overleaf 25M+/30M users" | Overleaf's own about page says **"20 million+ users"** and also **"over 30 million people trust Overleaf"** — internally inconsistent. | 20M+, quoting the smaller explicit figure and saying which one |

The GPT-4o (19.9% / 45.4%) and GPT-3.5 (55% / 43%) figures in the pitch script **do** hold up and
are retained.

---

## 8. Sources

**Citation accuracy.** Baethge & Jergas 2025, *Res Integr Peer Rev* 10(1):13 · Jergas & Baethge 2015,
*PeerJ* 3:e1364 · Mogull 2017, *PLOS ONE* 12(9):e0184727 · George & Robbins 1994, *J Am Acad Dermatol*
31(1):61–64 · Lukic et al. 2026, *Front Anesthesiol* · Buijze et al. 2012 · Greenberg 2009, *BMJ*
339:b2680 · Tatsioni et al. 2007, *JAMA*.

**Peer review's limits.** Baxt et al. 1998, *Ann Emerg Med* · Schroter et al. 2008, *J R Soc Med* ·
*BMJ* 2023;383:e076441.

**Retractions.** Retraction Watch database + Crossref announcement 12 Sep 2023 · *J Inf Sci* 2026
(994 Nature Index articles) · *JAMA Netw Open* 2024 (microRNA) · *JAMA Netw Open* 2019 (Wakefield) ·
*Science* Jan 2021 (Surgisphere) · *Scientometrics* 2022 (Reuben).

**AI-fabricated references.** *Lancet* 2026 (2,471,758 PMC articles / 125.6M references), reported in
*Nature* · Linardon et al. 2025, *JMIR Ment Health* 12:e80371 · Walters & Wilder 2023, *Sci Rep*.

**Market and demand.** STM & Research Consulting, 13 Jan 2026 (Dimensions data) · STM Global Brief
2021 (Outsell; UNESCO) · Clarivate SEC Form 10-K FY2025 · Global Info Research · YH Research ·
WiseGuyReports · Corporation for Digital Scholarship Annual Report 2024 · overleaf.com/about.

**Competitors.** scite.ai/features, scite.ai/pricing · Nicholson et al. 2021, *Quant Sci Stud*
2(3):882–898 · Bakker, Theis-Mahon & Brown 2023, *Hypothesis* 35(2) · Research Solutions press
release 27 Nov 2023 and SEC filings · Turnitin help centre and guides · iThenticate user guide and
pricing · ReciteWorks FAQ · US Naval Postgraduate School plagiarism guide · arXiv 2609.07652
(RefVerifier) · EditVerse pricing.

**ClaimTrace.** `claimtrace/docs/audit-contract.md` §2, §4 · `claimtrace/docs/engine-contract.zh-CN.md`.

---

## 9. The three sentences to remember

1. **One in six quotations is wrong, half of them seriously, and it has not improved in forty years.**
2. **Every tool on the market checks the paper; none checks the sentence.**
3. **We never turn a failed lookup into a verdict** — because the dangerous output is not a wrong
   answer, it is a reassuring one.
