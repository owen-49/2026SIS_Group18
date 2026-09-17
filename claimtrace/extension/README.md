# ClaimTrace Chrome Extension

Manifest V3 extension that detects BibTeX and `\\cite{...}` commands in Overleaf. It opens a searchable bibliography in Chrome's Side Panel and runs bibliography existence/metadata Audit against the local ClaimTrace backend.

## Load in Chrome

1. Open `chrome://extensions`.
2. Enable **Developer mode**.
3. Select **Load unpacked**.
4. Choose this `extension` directory.
5. Open an Overleaf project and select a `.bib` file to link the bibliography.
6. Click the ClaimTrace toolbar action or the in-editor prompt.
7. Open a `.tex` file. Lines containing supported citation commands highlight on hover; use the **Citations** tab to locate them from the Side Panel.

The extension starts with four demo sources. When it can read BibTeX from the active Overleaf editor, the detected `.bib` content is uploaded to `http://localhost:8000/api/parse`, then sent to `POST /api/audit` using its `bib_paper_id`. Audit results are shown beside bibliography entries and citation locations.

PDF uploads remain part of the web audit workspace. The Side Panel lists completed uploaded PDFs and can run the same Audit contract with the selected PDF's `manuscript_id`. The extension does not run claim-support Verify: citation highlights remain navigation aids and display only the matching bibliography Audit status.

## Audit contract

The extension sends exactly one input identifier:

```json
{ "bib_paper_id": "uploaded-bib-id" }
```

or:

```json
{ "manuscript_id": "uploaded-pdf-id" }
```

Run regression tests with:

```sh
node --test claimtrace/extension/audit-flow.test.cjs
```

## Extension files

- `manifest.json` — Side Panel and Overleaf permissions
- `src/background.js` — panel behaviour and shared storage
- `src/content.js` — Overleaf BibTeX/citation detection, editor highlighting, and location handling
- `src/sidepanel.*` — searchable paper library and citation-location UI
