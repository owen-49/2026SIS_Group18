"""ClaimTrace Semantic Engine — Pair 2.

Core IP pipeline:
  1. Parse source PDFs → structured text (parser/)
  2. Parse .bib files → structured bibliography (bib_parser)
  3. Embed + index passages (embedder, retriever)
  4. Verify claims against source (verifier)
  5. Cross-check bib metadata vs PDF metadata (bib_verifier)
"""

__version__ = "0.1.0"
