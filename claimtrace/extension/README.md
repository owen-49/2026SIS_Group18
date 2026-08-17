# ClaimTrace Chrome Extension

Manifest V3 extension that detects BibTeX and `\\cite{...}` commands in Overleaf. It opens a searchable bibliography in Chrome's Side Panel and provides a local citation-location preview in the editor.

## Load in Chrome

1. Open `chrome://extensions`.
2. Enable **Developer mode**.
3. Select **Load unpacked**.
4. Choose this `extension` directory.
5. Open an Overleaf project and select a `.bib` file to link the bibliography.
6. Click the ClaimTrace toolbar action or the in-editor prompt.
7. Open a `.tex` file. Lines containing supported citation commands highlight on hover; use the **Citations** tab to locate them from the Side Panel.

The extension starts with four demo sources. When it can read BibTeX from the active Overleaf editor, the demo library is replaced with the detected entries.

Citation verdicts are deterministic local preview signals. The extension does not call the backend and does not claim that these verdicts are evidence-verified.

## Files

- `manifest.json` — Side Panel and Overleaf permissions
- `src/background.js` — panel behaviour and shared storage
- `src/content.js` — Overleaf BibTeX/citation detection, editor highlighting, and location handling
- `src/sidepanel.*` — searchable paper library and citation-location UI
