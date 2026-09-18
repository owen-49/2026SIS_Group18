# ClaimTrace Chrome Extension

Manifest V3 extension that detects BibTeX and `\\cite{...}` commands in Overleaf. It opens a searchable bibliography in Chrome's Side Panel and sends `.bib` metadata and matched citation claims to the local ClaimTrace backend.

## Load in Chrome

1. Open `chrome://extensions`.
2. Enable **Developer mode**.
3. Select **Load unpacked**.
4. Choose this `extension` directory.
5. Open an Overleaf project and select a `.bib` file to link the bibliography.
6. Click the ClaimTrace toolbar action or the in-editor prompt.
7. Open a `.tex` file. Lines containing supported citation commands highlight on hover; use the **Citations** tab to locate them from the Side Panel.

The extension starts with four demo sources. When it can read BibTeX from the active Overleaf editor, the detected `.bib` content is uploaded to `http://localhost:8000/api/parse`, and the bibliography is checked against any previously uploaded source PDFs. Matching citation claims are sent to `/api/verify` and their results are shown in the editor and Side Panel.

When the backend is unavailable, or when no uploaded PDF matches a bibliography entry, the extension keeps the citation visibly labelled as a local preview. PDF uploads remain part of the web audit workspace; the extension itself only reads `.tex` and `.bib` content from Overleaf.

## Bibliography Audit

Audit is added alongside the existing Verify workflow. A detected BibTeX file is
audited through `POST /api/audit` with its parsed ID:

```json
{ "bib_paper_id": "uploaded-bib-id" }
```

The Side Panel also lists completed PDFs already uploaded through the web
workspace. Selecting one and clicking **Audit PDF** uses:

```json
{ "manuscript_id": "uploaded-pdf-id" }
```

Audit results show publication existence, metadata differences, ambiguous
records, and lookup failures. They do not replace or alter claim-support Verify.

## Review ambiguous source PDFs

In the Citations tab, unresolved citations retain candidate PDFs under
**Review candidate PDFs**. Compare filenames, upload IDs, arXiv IDs, and title
similarity, then click **Choose this PDF and verify**. Title similarity is a
candidate ranking, not proof of identity. Explicitly conflicting arXiv IDs
cannot be selected. The selected upload ID is checked against the latest
backend list before verification.

Only a unique arXiv match or a sole exact-title candidate can be selected
automatically. Fuzzy-only matches require review, even with one candidate.
Manual selection applies to the current verification; re-detecting citations
requires review again if the source remains ambiguous.

Run regression tests with:

```sh
node --test claimtrace/extension/arxiv-matching.test.cjs
```

## Extension files

- `manifest.json` — Side Panel and Overleaf permissions
- `src/background.js` — panel behaviour and shared storage
- `src/content.js` — Overleaf BibTeX/citation detection, editor highlighting, and location handling
- `src/sidepanel.*` — searchable paper library and citation-location UI
