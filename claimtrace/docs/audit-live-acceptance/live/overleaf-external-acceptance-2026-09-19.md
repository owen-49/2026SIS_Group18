# Real Overleaf + External Lookup Acceptance

Date: 2026-09-19
Mode: manual live acceptance with the real Overleaf plugin and backend
Status: passed

## Scope

This record supplements the older `live-evidence.json` files. Those JSON files
are preserved as historical Scholar-timeout evidence and are not overwritten.

## Accepted flow

1. The real Overleaf plugin read the active BibTeX bibliography and sent it to
   the backend.
2. Four BibTeX reference lookups completed through the external publication
   lookup flow.
3. The real PDF flow sent the manuscript to the backend and completed two
   citation/reference checks.
4. The BERT publication link opened the ACL Anthology page:
   `https://aclanthology.org/N19-1423`.
5. A citation placed on its own line displayed the surrounding sentence from
   the complete editor document instead of displaying only `\\cite`.

## Regression evidence

- Extension Node regression: 49 passed.
- Frontend lint: passed.
- Frontend production build: passed.
- Python Ruff checks for parser, engine, and backend: passed.

## Environment notes

- The committed `live/*.json` reports remain historical Scholar-era records and
  must not be interpreted as the result of this acceptance run.
- The latest manual result was observed through the real plugin/backend flow;
  no new request IDs or raw provider responses were captured in this repository.
- Backend PDF/parser regression tests require Java 11 or newer. The acceptance
  workstation used Java 8, so those local parser tests reported the known
  OpenDataLoader class-version failure; this does not invalidate the successful
  manual acceptance above.
