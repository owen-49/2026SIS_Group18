# ClaimTrace showcase package

Materials for a five-minute project presentation: a slide deck in two formats, an A1 poster in two
formats, and an interactive demo of the three core features.

> 中文版：[README.zh.md](README.zh.md)

| File | What it is | How to use it |
|---|---|---|
| `slides.html` | Eight-slide 16:9 deck, designed for the browser | Open in Chrome. `←` `→` navigate, `P` prints, click the left/right half of the slide |
| `ClaimTrace-Showcase.pptx` | The same deck as a real PowerPoint file | Open in PowerPoint, Keynote or Google Slides. Speaker notes are on every slide |
| `poster.html` | A1 portrait poster (594 × 841 mm) | Open in a browser for a fitted preview; print to A1 with margins set to none and background graphics enabled |
| `ClaimTrace-Poster-A1.pdf` | The same poster as a ready-to-print PDF, 594.1 × 841.0 mm | Send to a print shop or open in Preview; no setup needed |
| `rotating-poster.html` | Four-face 3D poster for a screen | Open in a browser. Drag to rotate, arrow keys turn it, it advances every 6.5 s. Deep-link a face with `#1`–`#4` |
| `demo.html` | Interactive demo of Audit, Verify and Read | Open in a browser. Tabs deep-link with `#audit`, `#verify`, `#read` |
| `theme.css` | Shared colour, type and chip tokens | Linked by the three HTML pages |
| `build_pptx.py` | Regenerates the `.pptx` from scratch | `python3 build_pptx.py` (needs `python-pptx`) |

Everything is self-contained: no fonts, scripts or styles are loaded from the network.

## The five-minute run-through

| Time | Slide | Say |
|---|---|---|
| 0:00 | 1 — Title | What ClaimTrace is, in one sentence. |
| 0:25 | 2 — Problem | The 48-hour complaint; the three personas asked for the same thing — evidence, not a conclusion. |
| 1:05 | 3 — Three checks | Audit the bibliography, verify claims against the source, read the paper in the same pane. |
| 2:00 | 4 — Architecture | The engine decides identity; the product never guesses. One process, two outbound boundaries. |
| 2:45 | 5 — Audit | Four real fixture cases. The two rows that matter are the ones where it refuses to answer. |
| 3:40 | 6 — Verify | The verdict is the headline; the passage is the argument. |
| 4:20 | 7 — Evidence | 1,130 tests, 34/34 controlled audit cases, 12/12 live verify cases, no server-side model key. |
| 4:50 | 8 — Close | Next steps and the ask. |

For a live demo, open `demo.html` after slide 3: run the audit replay, click a SUPPORT and a
NOT_FOUND claim, then show the Read pane.

## What is measured, and what is illustrative

Every number in the deck and poster is traceable:

- **1,130 tests** — backend 552, engine 378, parser 101 passed + 2 skipped, extension 49, frontend 50,
  at local `main` `e171fb3`.
- **34/34 audit cases** — `docs/accuracy-baseline/audit_accuracy_subset.json`, generated
  `2026-10-08T07:55:20+00:00`: state accuracy 1.00, macro-F1 1.00; per state 7 verified,
  12 metadata mismatch, 9 needs review, 1 not found, 2 lookup failed.
- **12/12 live verify cases** — six claims in two modes, DeepSeek, 12 model calls.
- **0.055 s per audit request** — `docs/accuracy-baseline/audit_timing.json`.
- **Audit rows** — `bert-exact`, `bert-year-plus-one`, `dialoguernn-year-minus-five` and `provider-500`
  are real cases from `backend/tests/benchmarks/audit_cases.json`.
- **Verify claims and passages** — the six claims and five source paragraphs come from
  `backend/scripts/acceptance_citation_comparison.py`; the quoted passages are verbatim from
  *Attention Is All You Need*.

Deliberately not claimed:

- These are **fixture labels**, not independent expert annotation. The deck says so on slide 7.
- No retrieval rank or similarity score is shown for the demo claims, because no recorded verify
  ranks exist in the repository (`recorded_claims/passages.json` has no pairs). The phrase
  "Retrieved from the cited paper · quoted verbatim" is used instead. The product does return
  `rank` and `similarity` in `ComparisonEvidence`; the *product* statement is accurate, but no
  invented numbers appear in the showcase.
- The Read pane in `demo.html` is an **illustrative excerpt**. The Markdown pipeline it shows
  (`rehype-raw` → `rehype-sanitize` → `rehype-katex`) and the image route
  (`GET /api/papers/{paper_id}/images/{filename}`) are the real ones. The figure is a schematic
  stand-in, labelled as such in the page.
- The supervisor quote is an English translation from the Chinese user research, marked
  "translated from user research".

## Printing the poster

`ClaimTrace-Poster-A1.pdf` is already A1 (594.1 × 841.0 mm) and needs no print setup — send it to
the print shop as it is. It was generated from `poster.html` with headless Chrome:

```sh
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless --disable-gpu \
  --no-pdf-header-footer --print-to-pdf=ClaimTrace-Poster-A1.pdf "file://$PWD/poster.html"
```

`poster.html` previews scaled to the window. In the browser's print dialog choose **A1**, set
margins to **None**, and enable **Background graphics**. The page declares
`@page { size: 594mm 841mm; margin: 0 }`; the preview scale is removed for print.

The rotating poster is for a screen only. For a booth loop, open `rotating-poster.html` full-screen;
it rotates on its own and pauses while hovered or dragged.

## Rebuilding the PPTX

```sh
cd claimtrace/showcase
python3 build_pptx.py
```

The builder uses `python-pptx` and the fonts Georgia, Arial and Courier New, so it opens without
substitution on macOS and Windows. Text fit and shape bounds were checked programmatically, but
the `.pptx` was **not rendered visually** on this machine (no LibreOffice). Open it once in
PowerPoint or Keynote before presenting; the HTML deck is the pixel-exact reference.
