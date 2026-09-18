# The claim-passage benchmark

Two numbers in the preparation plan are commitments rather than descriptions:

| metric | Go | No-Go |
|---|---|---|
| Recall@5 — the ground-truth passage is in the top 5 retrieved | ≥ 0.80 | < 0.50 |
| Recall@1 | ≥ 0.50 | < 0.25 |
| Accuracy, four classes | ≥ 0.80 | — |
| F1, Support vs Rest | ≥ 0.85 | — |
| Cohen's Kappa | ≥ 0.70 | — |

`engine/passage_eval.py` is the instrument that turns a set of annotated pairs
into those numbers, `passage_harness.py` runs it, and `claim_passages.json` is
where the pairs go.

## That file is empty, on purpose

An instrument is not a measurement. The loader, the scoring, the bars and the
report can all be built and tested — and are — but **the labels are the team's**.
They are human judgements about whether a paper's text supports a claim made
about it, and writing them here would produce a number that measures whoever
wrote them. `[]` is the honest state of the file until the annotation happens,
and the harness says so rather than reporting 0%.

## The protocol

The plan's protocol is five test PDFs, ten pairs each. One pair is:

1. a **claim**, a sentence from a citing manuscript, as written;
2. a **source paper**, the work that sentence cites;
3. a **source passage**, the sentence or two in that paper which carries the
   claim — marked by a person who has read both;
4. a **label**, one of `SUPPORT` / `PARTIAL` / `CONTRADICT` / `NOT_FOUND`, and one
   sentence saying why.

The annotation guidelines are in `README.md`. Read them before starting; the
short version is that `PARTIAL` is for a claim that overstates or drops a caveat,
and it is the most actionable label for an author.

### Working recipe

The corpus comes from the parsed papers under `backend/uploads/parsed/`, so the
source paper must be **in the library** before its passage can be marked. Upload
the cited PDFs first.

Then, for each citing manuscript:

1. Read it and pick ten sentences that cite a paper you have uploaded.
2. For each one, open the cited paper and find the passage that decides it.
3. Write the pair into `claim_passages.json`:

```json
[
  {
    "claim": "There has been extensive previous work proposing architectures to enrich systems with non-parametric memory which are trained from scratch for specific tasks, e.g. memory networks [64, 55], stackaugmented networks [25] and memory layers [30].",
    "source_passage": "the sentence in the cited paper, copied from it",
    "label": "SUPPORT",
    "source_paper": "f940bcbf",
    "citing_paper": "92574678",
    "annotator": "your name",
    "notes": "one sentence: why this label"
  }
]
```

`source_paper` is the paper's id in `backend/uploads/parsed/`, or any unambiguous
prefix of it. `source_passage` is matched as a **substring** of the retrieved
paragraph, so a sentence is enough and a whole paragraph also works; it is
compared after case folding and whitespace collapsing, so a line break copied
from a PDF viewer will not break it.

`label` may be left as `""` for a pair someone has started but not finished. Such
a pair is held out of every metric and counted as unannotated, which is why a
half-filled file cannot be reported as a measured one.

### A first pair, waiting to be annotated

A scan of every `*.references.json` in the library, looking for a reference whose
text quotes another library paper's title, returns exactly one hit: `92574678`
(RAG, retrieval-augmented generation) cites `f940bcbf` ("Large Memory Layers with
Product Keys", Lample et al.) as reference 30, and the sentence citing it is
paragraph 39 of `92574678`:

> There has been extensive previous work proposing architectures to enrich
> systems with non-parametric memory which are trained from scratch for specific
> tasks, e.g. memory networks [64, 55], stackaugmented networks [25] and memory
> layers [30].

Both papers are already parsed, so this pair can be annotated today. It is the
one entry the corpus can support without new uploads — everything else needs the
cited PDFs added first. Re-run that scan after uploading PDFs to find the next
pair. The label is not written down here because it is the annotation, and the
point of the annotation is that a person reads both papers and decides.

Do not identify a library paper by its filename. `f940bcbf` is
`1907.05242v2.pdf`, and only the paper's own text says which work that is. Two
references in `92574678` look alike from a library listing — `[30]` memory layers
is the work in the library, `[47]` (Petroni et al.) is not — and pairing the
wrong one writes down a claim whose passage cannot exist in the paper it names.

## Running it

From `claimtrace/engine`:

```bash
# ask the retriever, and record what it returned
python tests/benchmarks/passage_harness.py --mode record --only retrieval

# ask the model, and record what it said (needs DEEPSEEK_API_KEY or OPENAI_API_KEY)
python tests/benchmarks/passage_harness.py --mode record --only entailment

# score from the recordings: offline, deterministic, no model, no network
python tests/benchmarks/passage_harness.py --mode replay
```

`--mode replay` is the one to read. It needs no network and no key, both halves
can be re-scored as annotations are corrected, and `--output report.json` writes
the same numbers as JSON for the weekly report.

## How to read the report

**The two halves are measured apart.** Retrieval is scored on the claim alone.
The judgement is scored against the passage the *annotator* marked, never
against what retrieval returned — otherwise a retrieval miss would be counted as
a judgement error and neither bar could say which half moved. The harness prints
their product as an end-to-end ceiling, and labels it as a product.

**Coverage comes before accuracy.** A pair the model did not judge — no client, a
failed call, an unusable reply — is an abstention, not a wrong answer: only one
of those is what the accuracy bar is about. Abstentions are counted and printed
beside accuracy, and the harness refuses to record the judgement half without a
client, because a file of `NO_CLIENT` results reads later as a measurement that
happened.

**Unscorable is not a miss.** A pair whose source paper has no text in the corpus
is held out of the retrieval denominator and named in the report. Loading the
PDF is a prerequisite, and a missing PDF must not be reported as a retriever
that failed to find a passage in it.
