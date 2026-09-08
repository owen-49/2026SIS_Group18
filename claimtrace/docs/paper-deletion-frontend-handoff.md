# Uploaded Paper Deletion — Frontend Handoff

## Purpose

The backend now allows the Library page to permanently delete a locally uploaded PDF or BibTeX file.

## API contract

Use the `paper_id` returned by `GET /api/papers`.

```http
DELETE /api/papers/{paper_id}
```

### Success

```http
204 No Content
```

The response body is empty. After a successful deletion, remove the item from the Library view or reload the list with `GET /api/papers`.

### Paper not found

```http
404 Not Found
Content-Type: application/json

{"detail":"Paper not found."}
```

### Deletion failure

```http
500 Internal Server Error
Content-Type: application/json

{"detail":"Unable to delete the paper and its local artifacts."}
```

If deletion fails, keep the item in the Library and show the error to the user.

## Required frontend behaviour

1. Show a delete action for both PDF and BibTeX items in the Library.
2. Ask the user to confirm before calling the API because deletion is permanent.
3. On `204`, remove the item from the UI or refresh `GET /api/papers`.
4. On `404` or `500`, keep the item visible and show an error message.
5. Prevent repeated clicks while the delete request is in progress.

## Example request

```ts
async function deletePaper(paperId: string): Promise<void> {
  const response = await fetch(
    `${API_BASE}/api/papers/${encodeURIComponent(paperId)}`,
    { method: "DELETE" },
  );

  if (response.status === 204) return;

  const body = await response.json().catch(() => null);
  throw new Error(body?.detail ?? "Unable to delete the paper.");
}
```

## What the backend deletes

For the selected Library record, the backend removes its local upload, Library metadata, and generated files such as parsed JSON. For PDFs, related Markdown, extracted images, reference data, and audit results are also removed when present. Files belonging to other Library items are not deleted.

## Acceptance checks

- Deleting a PDF returns `204` and it disappears from `GET /api/papers`.
- Deleting a BibTeX file returns `204` and it disappears from `GET /api/papers`.
- Refreshing the page does not bring a deleted item back.
- Deleting an unknown or already deleted ID returns `404`.
- A failed request does not remove the item from the current Library view.

## Backend validation

- Full backend test suite: **81 passed**.
- Backend Ruff check: **passed**.

