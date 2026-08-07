# ClaimTrace Spike Reports

This directory contains technical spike reports that validate (or invalidate)
the most dangerous assumptions before Sprint 1 begins.

---

## Spike Schedule

| # | Hypothesis | Pair | Start | Due |
|---|-----------|------|-------|-----|
| 1 | RAG can locate the correct passage in dual-column PDFs (Recall@5 ≥ 0.80) | Pair 1 + 2-A | W1 | W2 Fri |
| 2 | LLM can reliably judge claim-support entailment (Accuracy ≥ 0.85) | Pair 2-B | W1 | W2 Fri |
| 3 | Overleaf DOM allows stable hover-triggered popup injection | Pair 3-B | W1 | W2 Fri |

---

## Report Template

```markdown
# Spike Report: [Hypothesis]

- **Date**: 
- **Authors**: 
- **Hypothesis**: 
- **Go Threshold**: 

## Method
...

## Results
| Metric | Value | Threshold | Pass? |
|--------|-------|-----------|-------|
|        |       |           |       |

## Error Analysis
...

## Verdict: GO / NO-GO / GO-WITH-RISK

## Next Steps
...
```
