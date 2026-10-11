# DeepSeek live Verify acceptance — 2026-10-11

The account owner entered the API key at a hidden local prompt. The run used
real DeepSeek calls, cached sentence-transformers embeddings, FAISS retrieval
and the Verify route, with seeded parsed source/bibliography fixtures in an
isolated temporary library. No provider transport or retrieval was mocked.

## Configuration and provenance

- Started at: `2026-10-11T01:44:23.283995+00:00`.
- API checkout: PR #60 at `701fa66f919c0556547e12c9d2b8a624329e247c`.
- Acceptance harness: PR #61 implementation at `d0a888082e57cd7e56a7477388407a9ba681b460`, overlaid on the API checkout.
- Harness SHA-256: `4407b774264f5d77fb90b2b2275666f173643e53173c83d7b1dea73bca975879`.
- Provider/model: `deepseek` / `deepseek-flash`.
- Modes: disabled (2048 generated-token cap) and enabled with low effort (8192 cap).
- Shared budget: 20 attempted calls; actual attempts: **12**.
- Per-provider request timeout: 30 seconds; no automatic retries.
- Original local JSON SHA-256: `91e266e5cef877de98a6c2d2ba741d16ee9ce521332c91e352eb618462164260`.

The original JSON report remains local at
`.pr60-acceptance-validation/claimtrace/reports/deepseek-thinking-live.json`
under `audit-run-main/`; this file records its credential-free results for review.

## Actual versus expected

Every row below also passed HTTP 200, COMPARED, source ID and nonempty-evidence
checks. All six paired cases returned identical retrieved-evidence hashes.

| Case | Expected | Disabled actual | Low-thinking actual | Result |
| --- | --- | --- | --- | --- |
| support | SUPPORT | SUPPORT | SUPPORT | Both passed |
| contradict | CONTRADICT | CONTRADICT | CONTRADICT | Both passed |
| not_found | NOT_FOUND | NOT_FOUND | NOT_FOUND | Both passed |
| partial_tasks | PARTIAL | PARTIAL | PARTIAL | Both passed |
| causal_not_found | NOT_FOUND | NOT_FOUND | NOT_FOUND | Both passed |
| training_contradict | CONTRADICT | CONTRADICT | CONTRADICT | Both passed |

| Mode | Passed | Failed | Selected untested | Mean elapsed seconds | Input tokens | Generated tokens | Reported reasoning tokens | Total tokens |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Disabled | 6 | 0 | 0 | 1.373 | 2280 | 409 | Not reported | 2689 |
| Low thinking | 6 | 0 | 0 | 1.262 | 2424 | 793 | 464 | 3217 |

Across the selected cases: **12 passed, 0 failed, 0 untested**. Provider usage was
reported for all 12 calls: 4704 input tokens, 1202 generated tokens and 5906 total
tokens. Reasoning is a breakdown of generated usage, not an extra amount to add
to that total. These counters are not a verified dollar bill.

The full installed-provider matrix contains **12 passed, 0 failed, 96 untested**.
The 96 untested cases belong to the other 16 providers (six cases each): OpenAI,
Anthropic, Gemini, xAI, Mistral, Cohere, Qwen, Moonshot, Zhipu, MiniMax, Doubao,
Groq, Together, Fireworks, SiliconFlow and OpenRouter. This run makes no claim
about those accounts.

## Interpretation and limits

Both modes passed this six-case smoke suite. There is no observed accuracy
advantage for either mode on these cases. Low thinking generated more tokens,
and the reported 464 reasoning tokens confirm that thinking was exercised.
The first disabled case took 2.909 seconds and includes initial embedding-model
loading; aggregate elapsed times cannot establish which mode is faster.

These are manually labelled cases against short seeded excerpts, with one run
per mode. They do not establish performance on a representative annotated corpus
or justify a product-wide default. PDF parsing, Audit AI extraction, deployed
server networking and browser key-entry behavior remain outside this suite.

The local `fitz` deprecation warning did not prevent this run from completing.
No API keys, provider response bodies, rationales or reasoning text are included
in this record.
