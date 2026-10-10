# Verify acceptance

`backend/scripts/acceptance_citation_comparison.py` checks three labelled claims
against a seeded excerpt of *Attention Is All You Need*: SUPPORT, CONTRADICT and
NOT_FOUND. Each executed case must return HTTP 200, COMPARED, the expected verdict,
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

Current account/budget agreement: pending. No live provider acceptance results
are claimed by this change.

## Plan without calls

Run from `claimtrace/` with the backend, Parser and Engine dependencies installed:

```sh
python backend/scripts/acceptance_citation_comparison.py --report verify-plan.json
```

This makes no provider requests, does not prompt for a key, and does not load an
embedding model or seed storage. The report contains every installed provider
times the three cases, all marked untested. Provider choices come from
`UserAIConfig`: current main exposes OpenAI/DeepSeek; after PR #60 integrates,
the same script discovers all 17 providers. The plan exits with code 2.

## Run an agreed account

Example syntax only; these commands do not establish an account or budget:

```sh
python backend/scripts/acceptance_citation_comparison.py --live \
  --provider deepseek --model deepseek-chat --max-calls 3 \
  --report verify-deepseek.json

# After PR #60 is integrated, with an agreed regional Qwen account:
python backend/scripts/acceptance_citation_comparison.py --live \
  --provider qwen --model ACCOUNT_MODEL_ID --region singapore \
  --case support --max-calls 1 --report verify-qwen-support.json
```

Add `--workspace WORKSPACE_ID` only when supported by the account's Qwen region.
Provider/region/workspace validation reuses the API contract before any call.
`--case` can be repeated to select specific cases. Without it, all three cases
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
without credentials, call count and elapsed time per executed case.

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

## Validation record — 2026-10-11

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
