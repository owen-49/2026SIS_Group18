# claimtrace/docs — the current documents

**This directory holds current documentation only.** Every file here is expected to match
the code. When a change makes a document wrong, fix it in the same pull request.

Historical documents are **not** kept here. If you need the reasoning behind a past
decision — why Google Scholar was replaced, why a threshold was rejected, what a
previously-planned feature was meant to do — read `git log` and the pull request bodies.
That is where it lives, and it is more complete than a stale document ever was.

If you are about to add an eighth contract document, check first whether it belongs in one
of the six that exist. This directory grew to 24 files by adding one per handoff; the
number is not the point, but the duplication was.

---

## Index

| Document | Reader | Kind | What it answers |
| --- | --- | --- | --- |
| [architecture.md](architecture.md) | everyone | overview | How the system is layered, what the data flows are, which endpoints exist, **what is still missing** |
| [audit-contract.md](audit-contract.md) | Backend, Frontend, Extension | contract | Bibliography Audit v2: request/response, the five states, the provider chain, the identity rules, the measured limits |
| [engine-verify-contract.zh-CN.md](engine-verify-contract.zh-CN.md) | Engine, Backend | contract | The Engine's Verify input/output contract and how a failure is reported without inventing a verdict |
| [citation-comparison.zh-CN.md](citation-comparison.zh-CN.md) | Backend, Engine | contract | Claim × source-paper semantic comparison: statuses, failure handling, and the reasoning for each |
| [parser-handoff.md](parser-handoff.md) | Parser, Backend | contract | What the Parser promises (reference fields, conventions) and the one metadata gap still open |
| [frontend-handoff.md](frontend-handoff.md) | Frontend | contract | Web app routes, Audit/Verify behaviour from the client side, the extension contract, and the open deletion defect |
| [team.md](team.md) | everyone | reference | The four groups, directory ownership, success-criteria status, and how work is actually tracked |
| [user-research/personas.md](user-research/personas.md) | everyone | reference | Who the product is for |
| [user-research/user-stories.md](user-research/user-stories.md) | everyone | reference | The `US-0x` stories. Cited **by number** from `extension/src/content.js` and `extension/hover-card.test.cjs` — keep the numbering stable |
| [audit-live-acceptance/](audit-live-acceptance/) | Backend, reviewers | evidence | Committed acceptance runs: fixtures, recorded responses, and the manual Overleaf end-to-end record |
| [diagrams/](diagrams/) | everyone | artifact | A generated runtime-architecture diagram. **Not auto-regenerated** and may lag the code — `architecture.md` is authoritative |

Documents in Chinese are marked `.zh-CN.md`. They are contracts, not translations: each
exists in one language only, and there is no mirrored copy to keep in sync.

## The rule this directory exists to enforce

**A failed check is never reported as a negative finding.**

`NOT_FOUND` means "we searched and the thing is not there". It must never carry the
meaning "we could not search". Audit encodes this as five states rather than four;
Verify encodes it as `ComparisonStatus`, where only `COMPARED` carries a verdict. The
statement is quoted verbatim in
[audit-contract.md §2](audit-contract.md#the-rule-the-rest-of-the-repository-quotes) and
is referenced from `backend/src/models.py`, `engine-verify-contract.zh-CN.md` and
`citation-comparison.zh-CN.md`.

If you change anything in this directory, the most likely thing to get wrong is
accidentally presenting an unchecked result as a checked one.

## Before you write "not implemented"

This repository's actual documentation failure was **under-reporting completion**. Four
of the six gaps once listed in `architecture.md` §6 had already been closed, and two
rounds of work were assigned on that basis. Open the file. Run the command. Then write.
