"""Minimal real-LLM smoke test for DeepSeek entailment verification.

Runs 3 claim-passage pairs and prints the verdict, confidence, and rationale.
Loads .env manually (config.py does not auto-load dotenv).

Usage:
    python scripts/llm_smoke_test.py
"""

import os
import sys
from pathlib import Path

# ── Load .env ────────────────────────────────────────────
ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
if ENV_PATH.exists():
    for line in ENV_PATH.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())

# ── Build client ─────────────────────────────────────────
from engine.llm_client import build_llm_client
from engine.verifier import VerificationStatus, Verifier

provider = os.getenv("CLAIMTRACE_LLM_PROVIDER", "deepseek")
api_key = os.getenv("DEEPSEEK_API_KEY", "")
base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

client = build_llm_client(provider=provider, api_key=api_key, base_url=base_url)
print(f"provider={provider}  model={model}  client={'OK' if client else 'None (FAILED)'}")

if client is None:
    print("FAILED: client is None — check DEEPSEEK_API_KEY in .env")
    sys.exit(1)

verifier = Verifier(model=model)

# ── Test cases ───────────────────────────────────────────
cases = [
    {
        "name": "SUPPORT (预期被支撑)",
        "claim": "The model exhibits emergent abilities at scale.",
        "passage": "We observe that performance improves discontinuously with model size, consistent with the empirical signatures of emergence.",
    },
    {
        "name": "CONTRADICT (预期矛盾/夸大)",
        "claim": "Larger models always outperform smaller ones on every task.",
        "passage": "We find diminishing returns beyond a certain scale, and on some tasks smaller models are competitive with larger ones.",
    },
    {
        "name": "NOT_FOUND (预期无关)",
        "claim": "The proposed method improves image classification accuracy.",
        "passage": "This paper studies the convergence properties of stochastic gradient descent under non-convex objectives.",
    },
]

print("\n" + "=" * 60)
unjudged: list[str] = []
for c in cases:
    result = verifier.verify(c["claim"], c["passage"], client=client)
    print(f"\n[{c['name']}]")
    print(f"  claim:    {c['claim']}")
    # The status is printed first, and a verdict only when there is one: a
    # non-JUDGED status means no judgement was reached, which is not the same
    # as a NOT_FOUND verdict.
    print(f"  status:   {result.status.value}")
    if result.status is VerificationStatus.JUDGED:
        print(f"  verdict:  {result.verdict.value}  (confidence={result.confidence})")
    else:
        unjudged.append(c["name"])
    print(f"  rationale: {result.rationale}")
    # The exact text the model was shown. Printing it is the human-visible form
    # of "the source passage really did reach the model"; an empty value here
    # means the model was asked to judge nothing.
    print(f"  source_text_used: {result.source_text_used[:200]!r}")

print("\n" + "=" * 60)
if unjudged:
    print(f"FAILED: {len(unjudged)} of {len(cases)} case(s) reached no judgement:")
    for name in unjudged:
        print(f"  - {name}")
    sys.exit(1)
print(f"OK: all {len(cases)} cases judged.")
