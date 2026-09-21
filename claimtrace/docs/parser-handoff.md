# Parser — boundary, contract and the one open gap

Owner: Parser (Yi Jiang, Zheng Fu). Consumers: Backend, Engine.

This file states what the Parser promises the rest of the system and what it does not
yet do. It replaces the Parser sections of `backend-parser-extension-handoff.md` and
the fulfilled field request in `pdf-audit-parser-handoff.zh-CN.md`.

---

## 1. Package layout

`parser/parser/`

| Module | Role |
| --- | --- |
| `pdf_parser.py` | The entry point. `parse_pdf` → `ParsedPaper`. Runs OpenDataLoader, then reorders two-column pages, then recovers paragraphs. |
| `opendataloader_adapter.py` | Wraps the Java-based OpenDataLoader call. |
| `element_extractor.py` | Text blocks and their bounding boxes. |
| `markdown_converter.py` | Optional Markdown output. Empties `generated_markdown/` on every run. |
| `reference_extractor.py` | Earlier, simpler reference-list extraction. `Reference` at `:12`. |
| `reference_json_extractor.py` | The current reference-list extractor. `Reference` at `:442`, `extract_references` at `:1224`. |
| `citation_sentence_extractor.py` | Claim sentences around citation markers. |

`opendataloader_pdf` and a Java runtime remain hard requirements for PDF parsing; tests
that need them skip when absent.

## 2. The backend adapter

`backend/src/services/parser_adapter.py` calls `parser.pdf_parser.parse_pdf` and maps the
result onto the backend's stable `ParsedDocument` contract
(`backend/src/models.py`), which carries `authors`, `year`, `venue` and `doi` alongside
the paragraphs.

Two rules follow from this split:

- **The Parser package must not import from `backend/**`.** The adapter is the only place
  the two meet, and the Engine's tests enforce the same rule in the other direction.
- **`ParsedDocument` is the contract, not `ParsedPaper`.** The adapter is allowed to fill
  fields the Parser leaves empty, which is exactly what happens today (§4).

## 3. Reference extraction — delivered

The field request is done. `reference_json_extractor.Reference` carries, per entry:

```
reference_id, raw_text, number, page_start, page_end,
bounding_boxes, authors, year, title, venue, doi
```

The conventions below are the parts that are **load-bearing for Audit and Verify**,
not formatting preferences:

- **`title` is the field the lookup needs.** When it cannot be extracted, leave it empty.
  Never fall back to the whole reference string as the title — a full citation string as a
  title poisons the search with the very fields the comparison is about to check.
- **Never back-fill an input field from a search result.** The compared values must be the
  reference's own; a value sourced from the record would agree with itself.
- **`authors` is an array of strings**, `Surname, Given name`; `year` is an integer or
  `null`; `venue` and `doi` are empty when not extracted.
- **An entry that fails extraction keeps its `raw_text`**, so it can still be shown and
  diagnosed. The raw text is also where the comparison falls back to (§4).
- **Numbering is the reference's own.** `number` comes from the printed marker, never from
  the entry's position in a `.bib` file — `[7]` must resolve to the reference printed as
  `[7]`.
- **Update both the dataclass and the exported JSON** so the two cannot disagree.

`extract_references` has two call paths: the tool-facing `reference_json_extractor.extract_references(pdf_path)`
and `reference_extractor.extract_references(pdf_path, parsed_paper)`. Backend uses the
former, and reuses it only when no persisted `{paper_id}.references.json` artifact exists.

### Supported styles

APA 7 and standard IEEE metadata are extracted into structured fields. Other recognised
styles keep the raw text with `title`/`authors`/`year`/`venue`/`doi` possibly `null`.

### Structural rules that reject input

- **A reference section needs at least two entries.** Enforced in several places
  (`:806`, `:1136`, `:1278`). A one-entry section is not extracted at all, so a
  single-reference sample returns zero results with a warning. This is deliberate — the
  heading detector cannot distinguish one reference from a body paragraph — and it is
  documented rather than changed. Use a multi-entry PDF as an acceptance sample.
- **The heading must be found.** A generated one-page reference-list PDF once ran cleanly
  and returned zero references with the warning "Reference-list heading was not found".
  Report that case rather than treating an empty list as a paper with no references.

## 4. The one gap still open: `ParsedPaper` first-page metadata

`ParsedPaper` (`parser/parser/pdf_parser.py:38`) declares `title` and `authors`. The
constructor call at `:231` sets neither: it passes `file_path`, `paragraphs`,
`raw_blocks` and `pages` only. So every parsed PDF reaches the adapter with
`title=None` and `authors=[]`.

**This is not currently causing visible breakage**, because the adapter fills those fields
from conservative first-page text heuristics. That fallback is the live implementation and
it is unowned: it was written as a stopgap and nobody has confirmed the Parser will
replace it. Treat it as the long-term metadata source until someone decides otherwise, and
do not cite the heuristics as a temporary measure in new work.

`ParsedPaper` also has no `year`, `venue` or `doi` field at all, so the adapter's fallback
is the only source for those regardless of what the Parser later does. Adding them is a
P2-level Parser change with no committed owner.

## 5. Where the audit actually reads from

Measured over the 174 PDF references under `backend/uploads/parsed`: the structured
`title` is non-empty for **exactly one**, while the raw text yields a title for **173**.

So although the structured fields exist and are correct when populated, on the real corpus
they are effectively empty, and Audit reads the raw text. That is why
`docs/audit-contract.md` §4 has a rule for values recovered from raw text at all, and it is
the strongest available argument for finishing §4: fixing the Parser's structured output
would not remove the recovered-value rule, but it would make the rule apply far less often.

The number is corpus-relative and drifts. Re-measure before quoting it.

## 6. Related contracts

- The Engine's reference-list consumption: `docs/engine-contract.zh-CN.md`.
- Why Audit reads raw text and what it does with it: `docs/audit-contract.md` §4.
- The deprecated standalone `/api/verify/bib` flow, which compares a `.bib` against an
  uploaded PDF's first-page metadata: `docs/audit-contract.md` §8.
