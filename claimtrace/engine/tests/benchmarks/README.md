# ClaimTrace Engine Benchmark

This directory contains ground-truth claim-passage pairs used to
evaluate the accuracy of the Semantic Lineage Engine.

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
