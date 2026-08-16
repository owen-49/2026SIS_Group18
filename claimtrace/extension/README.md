# ClaimTrace Chrome Extension

Manifest V3 extension that detects BibTeX content in Overleaf and opens a searchable bibliography in Chrome's Side Panel.

## Load in Chrome

1. Open `chrome://extensions`.
2. Enable **Developer mode**.
3. Select **Load unpacked**.
4. Choose this `extension` directory.
5. Open an Overleaf project and select a `.bib` file.
6. Click the ClaimTrace toolbar action or the in-editor prompt.

The extension starts with four demo sources. When it can read BibTeX from the active Overleaf editor, the demo library is replaced with the detected entries.

## Files

- `manifest.json` — Side Panel and Overleaf permissions
- `src/background.js` — panel behaviour and shared storage
- `src/content.js` — Overleaf/BibTeX detection
- `src/sidepanel.*` — searchable paper library UI
