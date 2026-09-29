# Audit export for the venue-abbreviation measurement

Hi Siyuan — here are the audit files. Three things in here will save you time, so please read
this before running the tool.

## What's in the package

| Path | What it is |
|---|---|
| `audits/` | All 24 audit JSON files, byte-identical to `backend/uploads/parsed/audits/` |
| `venue-records.csv` | The matched records flattened to one row per record, with the fields your tool needs |
| `audit-inventory.csv` | One row per audit file: entry count, match count, status counts |

`venue-records.csv` is the one to start from. It has 117 rows, `input_raw_text` (the bibliography
line as written in the manuscript) and `source_venue` (the authoritative venue from Crossref or
OpenAlex) side by side, which is the pair your measurement needs.

## Three things that will bite you

### 1. You will get 90, not 91

The count depends on how you deduplicate, and the data supports three different answers:

| Definition | Count |
|---|---|
| Raw matched rows (every `matched_record` in every file) | **117** |
| Unique `record_id` | **90** |
| Unique DOI (normalised) | **88** |

The gap between 117 and 90 is real: **one manuscript was audited 13 times, another 5, two more
twice** — 24 files covering only **6 distinct papers**. The same record therefore appears up to
three times. I've added an `is_primary` column marking the first occurrence of each `record_id`, so
you can reproduce any of the three numbers deliberately.

If you got 91, you're probably counting one row that dedup removes — worth reconciling before you
write the number into Section 7, because 90 vs 91 is the kind of thing a marker checks.

### 2. `entry.metadata.venue` is empty — do not read the input venue from there

This is the one that will silently break the measurement. On the **input** side, every field except
`raw_text` is empty:

```json
"metadata": {
  "key": "1", "entry_type": "misc", "title": "", "authors": [], "year": null,
  "venue": "", "volume": "", "number": "", "pages": "", "doi": "", "url": "",
  "publisher": "",
  "raw_text": "[1] Bastian Epping, Alexandre René, Moritz Helias, and Michael T. Schaub. 2024.
                Graph Neural Networks Do Not Always Oversmooth. In Advances in Neural Information
                Processing Systems (NeurIPS), Vol. 37. 48164–48188."
}
```

So if your tool reads `metadata.venue` on the input side it will find an empty string in every
single record and the measurement will return nothing. The manuscript's own venue spelling has to be
parsed out of `raw_text` — which is also where the abbreviation actually is, so this is the correct
source anyway.

The **source** side is populated and always the full form:

```json
"matched_record": { "provider": "crossref", "record_id": "crossref:10.52202/079017-1526",
  "metadata": { "venue": "Advances in Neural Information Processing Systems 37", ... } }
```

Both providers use the same `venue` key — I checked all 117 rows, Crossref and OpenAlex alike — so
there's no per-provider branching to write.

### 3. Only 5 of the 24 files contain anything

Nineteen of the 24 audits produced **zero** matched records (they are the older runs, before the
provider chain was wired up). All 117 rows come from five files, covering three papers:

| Audit file | Matched |
|---|---|
| `083cab62-d5e2-43bb-bc90-11fe584e7e1e.json` | 42 |
| `11e85907-a12a-4dbf-b65a-341e865772c1.json` | 37 |
| `34784dd4-37fb-499f-a200-9db35b87418b.json` | 13 |
| `1cf98b95-fc47-4e33-870c-2eea29c16700.json` | 13 |
| `d6db6492-1ea7-482b-b14c-897f71324ee7.json` | 12 |

`audit-inventory.csv` lists all 24 so you can confirm which to include. **Decide explicitly whether
your n is 3 papers or 90 records** — if three papers are carrying the result, say so in Section 7
rather than reporting it as 90 independent observations.

## One caveat on the data itself

Many rows are `NEEDS_REVIEW` rather than `VERIFIED` — across the whole set the statuses are 441
NEEDS_REVIEW, 301 LOOKUP_FAILED, 6 VERIFIED, 12 NOT_FOUND. A `matched_record` exists even when the
audit status is `NEEDS_REVIEW`, so filter on `audit_status` deliberately rather than assuming a
match means a confirmed one. I left the column in for that reason.

## Provenance

Copied 2026-09-29 from `claimtrace/backend/uploads/parsed/audits/` (gitignored via
`claimtrace/.gitignore:31`, which is why they aren't in the repo). Contents are bibliographic
records only — no manuscript body text; the longest free-text field is a 376-character bibliography
line. Nothing in here should be committed.
