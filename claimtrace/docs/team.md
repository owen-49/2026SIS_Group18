# Team, ownership and process

> Last reconciled against git history: 2026-09-21

This file replaces `team-charter.md` (which was still an unfilled `[TBD]` template) and
`jira-workflow.md` (587 lines describing a tool the team does not use).

---

## 1. The team

Course: 41129 Software Innovation Studio, UTS, 2026 Spring. Project: ClaimTrace.
Seven people in **four working groups**.

| Group | Members | GitHub | Owns |
| --- | --- | --- | --- |
| **Backend** | Hongyang Chen, Siyuan Sun | `chy1145141919810`, `Archieee-coderr` | `claimtrace/backend/` |
| **Frontend** | Jun Li, Sam | `Li-Jun-Li0577`, `Sam20051512` | `claimtrace/frontend/`, `claimtrace/extension/` |
| **Parser** | Yi Jiang, Zheng Fu | `johnnyjiangyi01-code`, `Fzddx` | `claimtrace/parser/` |
| **Engine** | Sichen Liu (solo) | `owen-49` (git `SichenLiu`) | `claimtrace/engine/` |

Ownership maps to **directories, not to layers of a stack**. A change that crosses a
directory boundary needs the owning group's review, which is the reason the contracts in
`docs/` exist and are written down.

Earlier handoff documents also name **Yiyang Yuan** as the owner of the extension
end-to-end check. No committed file maps that name to a GitHub handle; the second
Frontend member appears in git as `Sam20051512`. Confirm which before assigning extension
work by name.

### Three descriptions in this repository are wrong

They are recorded here so nobody re-derives work from them:

- the old `team-charter.md` used a `Pair 1/2/3 + Solo` scheme that never existed;
- the old `jira-workflow.md:3` said "Engine 4 / Backend 2 / Frontend 1";
- `docs/architecture.md` used to say three teams (Frontend / Backend / Engine+Parser).

The four-group split above is the only correct one.

---

## 2. Success criteria

From the original charter. The ownership column is filled in against the **real** split,
not the charter's template.

| # | Criterion | Owner | Status |
| --- | --- | --- | --- |
| 1 | ≥ 3 real PhD students/researchers try ClaimTrace before W10 | **none assigned** | No evidence in the repository. `docs/user-research/` holds personas and stories but no `interviews/` and no `findings.md`; the recorded research is desk work, not sessions with researchers. |
| 2 | A non-technical viewer understands the product value within 2 minutes of demo video | **none assigned** | The pitch artifacts exist (`Project pitch.pptx`, `Project pitch8.21.pdf`, `ClaimTrace-Pitch-Script-and-QA.md`). No comprehension check was run. |
| 3 | Every member can point to one thing they learned their degree wouldn't have taught them | **none assigned** | Not collected anywhere. |
| 4 | Parser Recall@5 ≥ 0.80 on held-out test PDFs | Parser | **Instrument exists, no data.** `engine/passage_eval.py` scores it and `engine/tests/benchmarks/CLAIM_PASSAGES.md` fixes the bars (Recall@5 ≥ 0.80 to proceed, < 0.50 to stop; Recall@1 ≥ 0.50). `claim_passages.json` is empty on purpose — the labels are the team's to write. |
| 5 | Entailment accuracy ≥ 85% on 50-pair benchmark | Engine | **Instrument exists, no data.** Same harness: accuracy ≥ 0.80, F1 (Support vs Rest) ≥ 0.85, Cohen's Kappa ≥ 0.70. Needs 50 annotated pairs; none written. |

Criteria 4 and 5 are blocked on **annotation labour, not tooling**. The measurement code
is built and tested; what is missing is a labelled set. That is a task someone can start
today with no dependencies.

Criteria 1, 2 and 3 were the charter's "Solo: Product & Quality" row. **That role has no
counterpart in the real four-group split**, so all three are currently unowned. They are
also the three the course assesses qualitatively, so the useful move is to assign them
rather than to note the gap again.

---

## 3. Process as actually practised

**Work is tracked by pull requests, not by Jira.** The repository has **zero** GitHub
issues and 44+ merged PRs. Every merged change arrived as a PR with a description stating
scope, what was deliberately not changed, and the validation performed. When you need to
know why something is the way it is, read the PR body and `git log` — not an issue
tracker.

The former `jira-workflow.md` described an Epic/Story/Task/Bug hierarchy, four issue
templates, a Story Point calibration table and a Sprint cadence. **None of it was ever
used**, and the document is deleted rather than kept as an aspiration. Do not recreate it:
a tracker with no entries is worse than no tracker, because it looks like process.

### Conventions that are actually enforced

- Every PR carries a description of scope and validation, including what was **not**
  changed. This has repeatedly been the thing that made a review possible.
- **A change to a documented contract updates the document in the same PR.** The
  contracts live in `docs/` and are the only reason four groups can work in four
  directories without breaking each other.
- **Docs are verified against code, not against other docs.** The failure mode this
  repository actually hit is documentation that *under-reported* completion: three closed
  gaps stayed listed as open for weeks, and work was assigned twice on that basis. Before
  writing "not implemented", open the file.
- Python: `ruff` (line length 100), tests required for new behaviour. JS/TS: `eslint` +
  `prettier`. CI must pass before merge.

### Test commands

```sh
cd claimtrace
python -m pytest backend/tests -q                    # backend — needs claimtrace/ as cwd
cd engine    && python -m pytest tests -q            # engine — no PYTHONPATH needed
cd parser    && PYTHONPATH=.. python -m pytest tests -q
cd ../frontend && npm run test:integration           # Playwright, own server on :3100
cd ../extension && node --test extension/*.test.cjs  # must be a glob, not a directory
```

Never import from `backend/**` in `engine/` or `parser/` code or tests — the boundary is
enforced in the Engine's tests.

---

## 4. Cross-group contracts

Whoever owns a directory owns its side of these. Each contract has one document:

| Contract | Document | Owner |
| --- | --- | --- |
| Audit v2, five states, provider chain, lookup rules | `docs/audit-contract.md` | Backend |
| Verify and citation comparison, Engine evidence | `docs/engine-verify-contract.zh-CN.md` | Engine |
| Claim × source-paper comparison | `docs/citation-comparison.zh-CN.md` | Engine |
| Parser output, reference fields, the open metadata gap | `docs/parser-handoff.md` | Parser |
| Web app and extension behaviour | `docs/frontend-handoff.md` | Frontend |
| System overview and known gaps | `docs/architecture.md` | all four |
