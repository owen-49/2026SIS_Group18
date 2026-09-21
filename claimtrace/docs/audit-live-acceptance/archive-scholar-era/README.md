# Scholar-era acceptance snapshots

These six files are the acceptance run recorded **2026-09-14**, when the metadata lookup
was Google Scholar scraping. Every lookup attempt in them names `google_scholar`, and the
failures are `SCHOLAR_TIMEOUT`.

They are kept because they record what actually happened at the time, and editing a record
to match later behaviour falsifies it. They were **moved here rather than overwritten**
when the snapshots were re-recorded against the current provider chain on 2026-09-21.

| File | What it is |
| --- | --- |
| `controlled-bib-response.json` | Audit response over the synthetic BibTeX fixture |
| `controlled-pdf-response.json` | Audit response over the synthetic PDF fixture |
| `controlled-evidence.json` | The assertions controlled mode made, and their outcomes |
| `live-bib-response.json` | Audit response over the real HTTP path |
| `live-pdf-response.json` | Audit response over the real HTTP path |
| `live-evidence.json` | The live run's cases |

**Read them as a record of 2026-09-14, not as current output.** The subsystem they
exercised — `google_scholar_lookup.py`, `bounded_scholar_lookup.py`, `scholar_worker.py`
and `engine/engine/scholar_search.py` — was deleted when Scholar was replaced rather than
repaired. See `../audit-contract.md` §3 for why, and §6 for how to read snapshots
generally.

The current snapshots are in `../controlled/` and `../live/`.
