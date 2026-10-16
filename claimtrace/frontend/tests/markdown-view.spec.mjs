import { test, expect } from '@playwright/test';

const png = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==',
  'base64',
);
const paper = (id, type) => ({ paper_id: id, file_type: type, original_filename: `${id}.${type}`, title: id, file_size: 100, status: 'completed', pages: 1, paragraph_count: 2, entry_count: 0, error_message: null, created_at: '', updated_at: '' });
const manuscriptDocument = () => ({ manuscript_id: 'manuscript', status: 'completed', claims: [], error_message: null, manuscript_document: { total_pages: 1, pages: [{ page: 1, heading: 'Manuscript', paragraphs: ['A selectable paragraph.', 'Another paragraph.'] }], matched_location: null } });

const markdown = `# Attention Is All You Need

The attention formula is

$$
\\text{Attention}(Q, K, V) = \\text{softmax}\\left(\\frac{QK^T}{\\sqrt{d_k}}\\right)V
$$

<table><thead><tr><th>Model</th><th>Layers</th></tr></thead><tbody><tr><td>base</td><td>6</td></tr></tbody></table>

![Figure](<manuscript_images/fig.png>)
`;

async function routeLibrary(page) {
  await page.route('**/api/papers', route => route.fulfill({ json: { total: 1, papers: [paper('manuscript', 'pdf')] } }));
  await page.route('**/api/papers/*/claims*', route => route.fulfill({ json: manuscriptDocument() }));
  await page.route('**/api/verify/sources', route => route.fulfill({ json: { total: 0, papers: [] } }));
  await page.goto('/verify');
  await page.locator('[data-selectable-paragraph]').first().waitFor();
}

test('manuscript panel switches between text view and rich Markdown view', async ({ page }) => {
  const imageRequests = [];
  await page.route('**/api/papers/*/markdown', route => route.fulfill({ json: { paper_id: 'manuscript', markdown } }));
  await page.route('**/api/papers/*/images/*', async route => {
    imageRequests.push(route.request().url());
    await route.fulfill({ body: png, contentType: 'image/png' });
  });
  await routeLibrary(page);

  // Text view is the default and keeps its selectable paragraphs.
  await expect(page.locator('[data-selectable-paragraph]').first()).toBeVisible();
  await expect(page.locator('.markdown-view')).toHaveCount(0);

  await page.getByRole('button', { name: 'Rich', exact: true }).click();

  const view = page.locator('.markdown-view');
  await expect(view).toBeVisible();
  await expect(view.locator('h1')).toContainText('Attention Is All You Need');
  await expect(view.locator('.katex-display')).toHaveCount(1);
  await expect(view.locator('table')).toBeVisible();
  await expect(view.locator('table')).toContainText('Layers');
  const image = view.locator('img');
  await expect(image).toBeVisible();
  await expect(image).toHaveAttribute('src', /\/api\/papers\/manuscript\/images\/fig\.png$/);
  expect(imageRequests).toHaveLength(1);

  // Switching back restores the selectable text view.
  await page.getByRole('button', { name: 'Text', exact: true }).click();
  await expect(page.locator('[data-selectable-paragraph]').first()).toBeVisible();
  await expect(page.locator('.markdown-view')).toHaveCount(0);
});

test('rich view surfaces a backend failure with a retry button', async ({ page }) => {
  await page.route('**/api/papers/*/markdown', route => route.fulfill({ status: 404, json: { detail: 'Markdown is not available for this paper.' } }));
  await routeLibrary(page);

  await page.getByRole('button', { name: 'Rich', exact: true }).click();

  await expect(page.locator('.markdown-view')).toHaveCount(0);
  await expect(page.locator('.manuscript-loading.error')).toContainText('Markdown is not available for this paper.');
  await expect(page.getByRole('button', { name: 'Try again' })).toBeVisible();
});

test('selecting text in the rich view feeds the claim search like the text view', async ({ page }) => {
  await page.route('**/api/papers/*/markdown', route => route.fulfill({ json: { paper_id: 'manuscript', markdown } }));
  await routeLibrary(page);

  await page.getByRole('button', { name: 'Rich', exact: true }).click();
  await expect(page.locator('.markdown-view')).toBeVisible();

  const paragraph = page.locator('.markdown-view p').first();
  await paragraph.selectText();
  await page.evaluate(() => {
    document.querySelector('.selection-manuscript')?.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
  });

  await expect(page.locator('.selected-citation-text blockquote')).toContainText('The attention formula is');
});
