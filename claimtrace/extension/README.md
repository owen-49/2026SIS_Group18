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
workspace. Selecting one and clicking **Check** uses:

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
node --test claimtrace/extension/*.test.cjs
```

## The citation hover card

Hovering a `\cite{...}` highlights the line and shows a card assembled from what
the page already has in memory: the claim the citation sits in, the bibliography
entry, and — once the claim has been verified against an uploaded PDF — the
passage `/api/verify` retrieved for it, with its rank among the matches and its
lexical overlap. An unverified citation shows the same card without the passage;
it does not show a spinner or an empty quote.

The card is built on the hover event from `chrome.storage` state. It opens no
connection and waits for nothing, which is what the one-second budget for
hovering a citation requires.

### Reading the latency on real Overleaf

`showCitationHover` takes a `performance.measure("claimtrace:hover")` on every
hover and prints it:

```
[ClaimTrace] hover card in 3.4 ms
```

Open DevTools on an Overleaf project, hover a citation, and read that line
(filter the console for `hover card`). It covers the card's construction and the
layout read that positions it, and stops before the browser paints the card.
Every measurement is also readable after the fact:

```js
performance.getEntriesByName("claimtrace:hover").map((entry) => entry.duration)
```

Numbers produced by the test sandbox are not latency measurements: `fake-dom.cjs`
has no clock, no layout and no paint, and only shows that the measurement is
taken and reported.

## Extension files

- `manifest.json` — Side Panel and Overleaf permissions
- `src/background.js` — panel behaviour and shared storage
- `src/content.js` — Overleaf BibTeX/citation detection, editor highlighting, and location handling
- `src/sidepanel.*` — searchable paper library and citation-location UI
- `fake-dom.cjs`, `*.test.cjs` — the page the content and background scripts are tested against, and their cases

## Audit retry and paper links

After opening a `.bib` file in Overleaf, use **Check references** to retry
without editing the file. Retry validates the cached upload and recreates it
only if the backend returns 404. This Audit path is independent of claim Verify.
Audit results expose identified publication links and clearly labelled
unconfirmed candidate links. Backend errors and report warnings remain visible.

The search box filters local entries. In Papers, **Search title on Google
Scholar** opens an external search page for the entered text; entries without a
URL offer the same title-search fallback. This is not a backend search API or
proof of publication identity. Backend alignment and current live-check limits
are recorded in [BACKEND_ALIGNMENT.zh-CN.md](BACKEND_ALIGNMENT.zh-CN.md).


## Reading and reviewing

The Papers tab groups the **Check references** action with an optional manuscript
check under **Check a manuscript instead**. The side panel has no backend banner
or dashboard footer link.

Hover over a citation to open a compact reading card. It stays open as you move
to the card, select text, or open the paper. Close it with **×**, **Escape**, or a
click outside; hovering over another citation switches the card. There is no pin
mode. The card shows the publication first, your cited sentence, and retrieved
evidence when available. Unverified citations say **Not checked** once.

Both the reading card and paper list resolve real entries from a safe HTTP(S)
URL, DOI (bare or doi.org URL), or arXiv eprint. Without an identifier, **Find
paper** opens a title search and does not claim an identified publication.
