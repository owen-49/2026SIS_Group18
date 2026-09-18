# ClaimTrace Engine Benchmark

This directory contains ground-truth claim-passage pairs used to
evaluate the accuracy of the Semantic Lineage Engine.

Two kinds of ground truth live here, with different formats: the claim-passage
pairs described below, and the reference-identity fixture the metadata provider
layer is measured against (see the last section).

## Format

Each file is a JSON list:
```json
[
  {
    "claim": "The model exhibits emergent capabilities.",
    "source_passage": "Performance improves discontinuously with scale...",
    "label": "SUPPORT",
    "source_paper": "wei2022emergent",
    "annotator": "name"
  }
]
```

## Labels

- `SUPPORT`: The source passage directly supports the claim.
- `PARTIAL`: Partial support — claim overstates or omits caveats.
- `CONTRADICT`: Source passage contradicts the claim.
- `NOT_FOUND`: Claim content not addressed in the source.

## Annotation Guidelines

1. Read the claim in context (from the citing paper).
2. Read the full source passage (not just the matched sentence).
3. Ask: "If I were a reviewer checking this citation, would I flag it?"
4. Label + write 1 sentence explaining your decision.
5. When in doubt, label `PARTIAL` — it's the most actionable for authors.

## Reference-identity fixture

`reference_identity_fixture.json` and `identity_harness.py` measure a different
question: given a reference as a manuscript wrote it, and the records OpenAlex
and Crossref return for it, did the engine pick the cited work? The thresholds in
`engine/identity.py` are meant to be measured rather than chosen, and this is the
instrument.

Each case carries the reference's raw text verbatim, a hand-checked query, and an
`expected` block. `acceptable_dois` is the answer that would be right, and
`forbidden_dois` / `forbidden_doi_prefixes` are records that must never be picked
— a superseded version of the paper, or a fabricated record. A case passes on
both, so answering "found" with the wrong record fails rather than counting as a
hit.

Cases drawn from a real reference are scored against `recorded/<case_id>.json`,
which is what the two providers actually returned. A case may instead carry its
own `candidates`, and does so only when its subject is a response the providers
do not return — a fabricated record arriving on its own rather than among real
ones. Those are marked by their case id and are not evidence of provider
behaviour; do not read them as such.

Run it from `claimtrace/engine`:

```bash
python tests/benchmarks/identity_harness.py --mode record   # re-query the providers
python tests/benchmarks/identity_harness.py --mode replay --sweep
```

`--mode replay` is offline and deterministic and needs no network. `--sweep`
re-scores the set at every value of a threshold constant and names each case whose
outcome changes, which is what turns "the threshold is 1" into something a
reviewer can check. `--query-source parsed` scores the reference parser and the
rule together instead of the rule alone, and prints both so the difference is
visible.
