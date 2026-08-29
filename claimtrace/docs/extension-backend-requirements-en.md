# Chrome Extension and Backend Integration Requirements

> Date: 29 August 2026
>
> Audience: Chrome extension developers

## Objective

Allow the extension to send BibTeX and citation information detected in Overleaf to the backend and display real backend verification results.

## Functional Boundary

- The extension supports `.tex` and `.bib` content;
- The extension does not upload or parse PDF files;
- Users upload PDFs through the web application, where they are stored in the local Library;
- The extension uses PDF records already available in the web Library;
- The extension reads `.tex` content and extracts citations. The backend does not currently require the complete `.tex` file to be uploaded.

## Backend Capabilities Available Now

- Receive and parse BibTeX files;
- Return a BibTeX paper ID and entry count;
- Return PDF and BibTeX records stored in the local Library;
- Verify BibTeX metadata;
- Verify an individual claim against a source PDF.

## Extension Requirements

1. Send BibTeX content detected in Overleaf to the backend.
2. Retain and use the BibTeX paper ID returned by the backend.
3. Use PDFs already uploaded through the web Library and do not add PDF upload functionality to the extension.
4. Correctly associate detected citation keys and claims with backend verification results.
5. Display real verification results returned by the backend.
6. Clearly show when the backend is unavailable, no source PDF exists, or PDF metadata is missing.
7. Clearly label demo results and never present them as real backend results.
8. Preserve the existing BibTeX detection, citation detection, and editor-location features.

## Backend Endpoints

- `GET /health`: Check whether the backend is available;
- `POST /api/parse`: Submit BibTeX content;
- `GET /api/papers`: Retrieve PDFs already available in the web Library;
- `POST /api/verify/bib`: Verify BibTeX metadata;
- `POST /api/verify`: Verify an individual claim.

## Current Expected Behaviour

The real PDF Parser has not yet been fully integrated. Some fields may therefore return `PDF_MISSING`. The extension should display this as unavailable PDF metadata rather than a system error.

## Acceptance Criteria

- The extension can successfully submit BibTeX content to the backend;
- The extension can use PDF records already available in the web Library;
- Backend results are associated with the correct citations;
- Users can distinguish real results, missing-data states, and demo results;
- The extension does not provide PDF upload functionality;
- Existing Overleaf detection and citation-location features continue to work.
