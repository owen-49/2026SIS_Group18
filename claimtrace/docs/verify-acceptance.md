# Verify acceptance

`backend/scripts/acceptance_citation_comparison.py` checks six labelled claims
against a seeded excerpt of *Attention Is All You Need*: SUPPORT, PARTIAL,
CONTRADICT and NOT_FOUND. Cases include overgeneralizing successful use on several
tasks to every task, an unsupported carbon-emissions causal claim, and an incorrect
GPU count. Expected labels follow the Engine's existing entailment definitions;
they are manually assigned fixture labels, not independent expert annotations.
Each executed case must return HTTP 200, COMPARED, the expected verdict,
the seeded source ID, and nonempty evidence with valid provenance fields.
A returned judgement alone does not pass the case.

## Agree the live run first

Before using `--live`, agree the provider, account model ID, region, optional Qwen
workspace, selected cases and budget with the account owner. Keep keys out of
chat, command arguments, configuration files, reports and version control.
Enter a key only at the script's hidden interactive prompt. The script does not
read provider credentials from `.env` or use the application's startup client.

`--max-calls` is a hard cap on attempted `UserAIRuntime.create` calls, including
any unexpected extra AI step. A failed call consumes one attempt. The existing
provider clients disable automatic retries. This cap is **not a dollar limit**;
agree costs and any account spending limit separately. Each normal fixture case
needs one call. Authentication, access, quota, rate-limit and unavailable-model
errors stop the account run, leaving later cases untested.

The account owner has authorized DeepSeek live acceptance with a relaxed budget.
The first comparison uses DeepSeek Flash, six cases in each of two modes (normally
12 calls), with a shared 20-call cap. Account credentials must still be supplied
locally. The first authorized live run completed: **12 passed, 0 failed, 0 selected
untested**, using 12 calls. See the [DeepSeek live validation record](verify-acceptance-deepseek-live.md)
for actual/expected results, token usage and the limits of this smoke comparison.

DeepSeek acceptance defaults to non-thinking mode with 2048 generated tokens.
`--thinking low`, `high` or `max` enables thinking with an 8192-token default.
`--max-output-tokens` overrides the per-call cap (1 through 32768).
`--compare-thinking` interleaves disabled and low for each selected case, sharing
one credential prompt and one call budget. It cannot be combined with `--thinking`.
The report records each row's mode, configured cap override and default caps.
These are harness overrides, not changes to the application's request defaults.
Incomplete completions fail even when they contain parseable JSON. Parameters
follow the [official DeepSeek Chat Completions API](https://api-docs.deepseek.com/api/create-chat-completion/).
Thinking requests omit temperature and explicitly set reasoning effort, following
the [official thinking-mode guide](https://api-docs.deepseek.com/guides/thinking_mode/).
The application's 30-second provider timeout remains in force. A timeout or
truncated response is a failed execution, not a valid semantic verdict.
The call cap resets on each invocation: track attempts across reruns separately.

## Plan without calls

Run from `claimtrace/` with the backend, Parser and Engine dependencies installed:

```sh
python backend/scripts/acceptance_citation_comparison.py --report verify-plan.json
```

This makes no provider requests, does not prompt for a key, and does not load an
embedding model or seed storage. The report contains every installed provider
times the six cases, all marked untested. Comparison planning adds a second mode
for DeepSeek. Provider choices come from
`UserAIConfig`: current main exposes OpenAI/DeepSeek; after PR #60 integrates,
the same script discovers all 17 providers. The plan exits with code 2.

## Run an agreed account

Example syntax only; these commands do not establish an account or budget:

```sh
python backend/scripts/acceptance_citation_comparison.py --live \
  --provider deepseek --model deepseek-flash --max-calls 20 --compare-thinking \
  --report verify-deepseek.json

# After PR #60 is integrated, with an agreed regional Qwen account:
python backend/scripts/acceptance_citation_comparison.py --live \
  --provider qwen --model ACCOUNT_MODEL_ID --region singapore \
  --case support --max-calls 1 --report verify-qwen-support.json
```

Add `--workspace WORKSPACE_ID` only when supported by the account's Qwen region.
Provider/region/workspace validation reuses the API contract before any call.
`--case` can be repeated to select specific cases. Without it, all six cases
for the selected provider are requested. Other providers/cases remain untested;
use separate report files for different accounts or models.

Live mode uses real sentence-transformers embeddings, FAISS retrieval, the
Verify HTTP route via TestClient, and the selected provider's real client. The
model may download on first use. Parsed PDF and bibliography fixtures are seeded
in a temporary library; PDF upload/parsing, deployed-server networking, browser
interaction and Audit extraction are outside this suite. Startup and deletion
recovery are deliberately not run, and storage globals are restored afterwards.

## Read the report

The console lists provider/case, outcome, expected verdict, actual verdict and
reason. JSON includes the revision, timestamp, scope, account configuration
without credentials, call count and elapsed time per executed case. Schema v2
adds a SHA-256 fingerprint of the harness, safe token-usage counters, per-mode
results, and hashes comparing retrieved evidence for paired cases. Raw evidence
and reasoning text are not copied. Missing usage is null, never assumed zero;
totals cover reported calls only, with counts of calls that lacked usage. Provider
token counters do not establish the billed dollar cost; consult account usage.
`mode_comparison` reports passed/failed/untested, completed API comparisons and
mean elapsed time. Timings include retrieval and initial model loading, so the
first case can be slower. `evidence_comparison` is true only when both modes
returned the same retrieved evidence; null means no complete pair was available.
Six smoke cases do not establish a statistically reliable quality advantage or
justify changing the product's default mode by themselves.

| Outcome | Meaning |
| --- | --- |
| passed | Executed and matched all comparison checks. |
| failed | Executed but returned the wrong verdict, incomplete/invalid comparison, HTTP error or request exception. |
| untested | Not selected, live mode disabled, credentials unavailable, setup prevented execution, interrupted, account stopped or budget exhausted. |

`summary` counts the entire provider/case matrix. `selected_summary` counts only
requested cases, so passing one account does not claim the other accounts pass.
Reports include allowlisted status/verdict/error codes and evidence counts;
raw provider bodies, messages, rationale and keys are not copied. The revision
identifies the API checkout; an uncommitted harness overlay must be recorded
alongside it when comparing branches.

Exit codes: **0** all selected cases passed; **1** at least one selected case
failed; **2** selected cases remain untested, or no cases were selected. Failure
takes precedence over incompleteness. A budget-blocked extra AI step leaves its
case untested because the comparison did not finish.

## Offline regression checks

```sh
PYTHONPATH=. pytest backend/tests/test_acceptance_citation_comparison.py -q
ruff check backend/scripts/acceptance_citation_comparison.py \
  backend/tests/test_acceptance_citation_comparison.py
```

Regression tests intercept provider HTTP traffic and fake retrieval. They check
the real API/Engine/SDK boundary, mismatched verdicts, incomplete comparisons,
report redaction, call limits, stopping accounts, continuation after a verdict
mismatch and storage restoration. These tests do not certify live accounts or
real embedding quality.

## Initial validation record — 2026-10-11

| Checkout and checks | Result |
| --- | --- |
| Main `1d4ffe5` with this harness: focused regressions | 25 passed; 2 provider-expansion checks skipped until PR #60 integrates. |
| PR #60 `701fa66` with this harness: complete backend suite | 505 passed, including all 27 new harness regressions. |
| Both checkouts: backend Ruff | Passed. |
| Main planning run | 0 passed, 0 failed, 6 untested; 0 provider calls. |
| PR #60 planning run | 0 passed, 0 failed, 51 untested; 0 provider calls. |

The SDK transport and retrieval in regression tests are replaced with offline
fixtures. The planning runs exercise report generation only. No real provider
accounts, real model inference, paid calls or deployed-server acceptance were
used in this validation. Existing FastAPI startup and Starlette/AnyIO
deprecation warnings remain.

DeepSeek follow-up: offline request checks cover the output cap, disabled
thinking, invalid cap rejection and partial-generation rejection. Real account
acceptance remains untested; compare account usage before/after the run to record
the provider's billed cost.
Focused follow-up checks: main 33 passed and 2 skipped; with PR #60's adapters,
all 35 harness checks passed.

Thinking-mode follow-up: main 43 focused tests passed and 2 provider-expansion
checks skipped; overlaid on PR #60 at `701fa66`, all 45 focused checks passed.
Regression checks cover interleaved modes, a shared budget, all
three thinking efforts, SDK request parameters, usage accounting, evidence
equality and exclusion of reasoning text and credentials. These checks use
mocked provider traffic, not real account inference.
