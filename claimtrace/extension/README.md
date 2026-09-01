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

## Files

- `manifest.json` — Side Panel and Overleaf permissions
- `src/background.js` — panel behaviour and shared storage
- `src/content.js` — Overleaf BibTeX/citation detection, editor highlighting, and location handling
- `src/sidepanel.*` — searchable paper library and citation-location UI
