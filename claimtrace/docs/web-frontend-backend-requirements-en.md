# Web Frontend and Backend Integration Requirements

> Date: 29 August 2026
>
> Audience: Web frontend developers

## Objective

Allow users to upload, view, and manage PDF and BibTeX files through the web application using real backend data.

## Backend Capabilities Available Now

- Upload PDF and `.bib` files;
- Store uploaded files and parsed results locally;
- Return PDF page and paragraph counts and BibTeX entry counts;
- Return all locally stored PDF and BibTeX records for the Library;
- Return BibTeX metadata verification results.

## Web Frontend Requirements

1. Allow users to upload both PDF and `.bib` files.
2. Display both PDF and BibTeX files in the Library.
3. Show page and paragraph counts for PDFs and entry counts for BibTeX files.
4. Reload uploaded PDF and BibTeX records from the backend after a page refresh.
5. Clearly display processing, completed, and failed states.
6. Display backend error messages when an upload or request fails.
7. Use real backend data and do not present mock data as real results.
8. Preserve all existing PDF upload and display behaviour.

## Backend Endpoints

- `POST /api/parse`: Upload and parse a PDF or BibTeX file;
- `GET /api/parse/{paper_id}`: Retrieve a file's processing status;
- `GET /api/papers`: Retrieve the local Library;
- `POST /api/verify/bib`: Verify BibTeX metadata.

## Current Expected Behaviour

The real PDF Parser has not yet been fully integrated. Some BibTeX verification fields may therefore return `PDF_MISSING`. This means that PDF metadata is not yet available; it does not indicate a frontend or API failure.

The current web integration scope covers PDF and `.bib` files. The backend does not currently accept complete `.tex` file uploads. Web upload support for `.tex` should be confirmed as a separate requirement if needed later.

## Acceptance Criteria

- Users can upload PDF and BibTeX files through the web application;
- Both file types appear in the Library after upload;
- BibTeX files display the correct entry count;
- Uploaded records remain visible after refreshing the page;
- Failed states and backend error messages are displayed clearly;
- Existing PDF functionality continues to work.
