import { test, expect } from '@playwright/test';

async function highlight(page, paragraph) {
  await paragraph.evaluate(async el => {
    await new Promise(requestAnimationFrame);
    el.scrollIntoView({ behavior: 'instant', block: 'center' });
  });
  const box = await paragraph.evaluate(el => {
    const range = document.createRange();
    range.selectNodeContents(el);
    const rects = [...range.getClientRects()];
    const first = rects[0], last = rects.at(-1);
    return { startX: first.x + 1, startY: first.y + first.height / 2, endX: last.right - 1, endY: last.y + last.height / 2 };
  });
  await page.mouse.move(box.startX, box.startY);
  await page.mouse.down();
  await page.mouse.move(box.endX, box.endY, { steps: 10 });
  await page.mouse.up();
}

test('storyboard example shows real image assets in Rich and compares a selected sentence', async ({ page }) => {
  const apiRequests = [];
  await page.route('http://127.0.0.1:8000/api/**', route => {
    apiRequests.push(route.request().url());
    return route.abort();
  });
  await page.goto('/verify/example');
  await expect(page.getByRole('button', { name: 'Rich', exact: true })).toHaveAttribute('aria-pressed', 'true');
  const view = page.locator('.markdown-view');
  await expect(view.locator('img').first()).toBeInViewport({ ratio: .9 });
  await expect(view.getByRole('heading', { name: 'BERT: Pre-training of Deep Bidirectional Transformers for Language Understanding', exact: true })).toBeAttached();
  for (const image of await view.locator('img').all()) {
    await image.scrollIntoViewIfNeeded();
    await expect.poll(() => image.evaluate(el => el.complete && el.naturalWidth > 0)).toBe(true);
  }
  await expect(view.locator('img')).toHaveCount(13);
  await expect(view.locator('img[alt*="Figure"]')).toHaveCount(5);
  await expect(view.locator('img[alt*="Table"]')).toHaveCount(8);
  await expect(view.getByRole('heading', { name: /^PDF page \d+ \/ 16$/ })).toHaveCount(0);
  expect(await view.locator('[data-selectable-paragraph]').evaluateAll(items => new Set(items.map(el => el.dataset.page)).size)).toBe(16);
  await page.getByRole('button', { name: 'Find citation', exact: true }).click();
  const sentence = view.locator('[data-demo-claim="true"]');
  await highlight(page, sentence);
  await expect(page.locator('.selected-citation-text')).toContainText('BERT’s model architecture');
  await page.getByRole('button', { name: 'Analyze selection', exact: true }).click();
  const result = page.getByRole('region', { name: 'Citation comparison result' });
  await expect(result).toContainText('Partial');
  await expect(result).toContainText('The encoder is composed of a stack');
  await expect(result).toContainText('Citation comparison');
  await page.getByRole('button', { name: 'Cited source', exact: true }).click();
  await expect(page.locator('[data-review-source-match="true"]')).toContainText('The encoder is composed');
  await page.getByRole('button', { name: 'Manuscript', exact: true }).click();
  await expect(view).toBeVisible();
  await expect(page.locator('.selected-citation-text')).toContainText('BERT’s model architecture');
  await page.getByRole('navigation', { name: 'Main navigation' }).getByRole('link', { name: 'Batch audit', exact: true }).click();
  await expect(page).toHaveURL(/\/audit\/example$/);
  expect(apiRequests).toEqual([]);
});

test('storyboard Audit runs the prepared example and opens its year mismatch', async ({ page }) => {
  const apiRequests = [];
  await page.route('http://127.0.0.1:8000/api/**', route => { apiRequests.push(route.request().url()); return route.abort(); });
  await page.goto('/audit/example');
  await expect(page.getByRole('button', { name: 'Run audit', exact: true })).toBeEnabled();
  await page.getByRole('button', { name: 'Run audit', exact: true }).click();
  await expect(page.locator('.audit-detail-panel')).toContainText('2016');
  await expect(page.locator('.audit-detail-panel')).toContainText('2017');
  await expect(page.locator('.audit-summary')).toContainText('56 references checked');
  expect(apiRequests).toEqual([]);
});

test('Rich sample figures fit a narrow viewport', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/verify/example');
  const view = page.locator('.markdown-view');
  await expect(view).toBeVisible();
  const image = view.locator('img').first();
  await image.scrollIntoViewIfNeeded();
  await expect.poll(() => image.evaluate(el => el.complete && el.naturalWidth > 0)).toBe(true);
  expect(await view.evaluate(el => el.scrollWidth <= el.clientWidth + 1)).toBe(true);
});


test('full published paper retains superscript footnotes and its original PDF', async ({ page, request }) => {
  await page.goto('/verify/example');
  const view = page.locator('.markdown-view');
  const claim = view.locator('[data-demo-claim="true"]');
  await expect(claim.locator('sup')).toHaveText('1');
  const annotated = view.locator('p').filter({ hasText: 'The Annotated Transformer' }).first();
  await expect(annotated.locator('sup')).toHaveText('2');
  const original = page.locator('.manuscript-toolbar').getByRole('link', { name: 'Original PDF', exact: true });
  const response = await request.get(await original.getAttribute('href'));
  expect(response.ok()).toBe(true);
  expect((await response.body()).subarray(0, 5).toString()).toBe('%PDF-');
  await expect(view).toContainText('C.2');
});


test('citations throughout the complete Rich paper respond to pointer clicks', async ({ page }) => {
  await page.goto('/verify/example');
  const links = page.locator('.markdown-view [data-citation-group]');
  await expect(links.first()).toBeAttached();
  expect(await links.count()).toBeGreaterThan(90);
  const selections = new Set();
  for (const link of await links.all()) {
    await link.click();
    const selected = page.locator('.selected-citation-text');
    await expect(selected).not.toContainText('Not yet selected');
    selections.add(await selected.innerText());
  }
  expect(selections.size).toBeGreaterThan(40);
});

test('SQuAD and ELMo selections use their own source passages and clear stale results', async ({ page }) => {
  await page.goto('/verify/example');
  const view = page.locator('.markdown-view');
  const squad = view.locator('p').filter({ hasText: /^The Stanford Question Answering Dataset/ });
  await squad.getByRole('link', { name: /Rajpurkar/ }).click();
  await expect(page.locator('.selected-citation-text')).toContainText('100k crowdsourced');
  await page.getByRole('button', { name: 'Analyze selection', exact: true }).click();
  const result = page.getByRole('region', { name: 'Citation comparison result' });
  await expect(result).toContainText('Support');
  await expect(result.locator('blockquote')).toContainText('100,000+ questions posed by crowdworkers');
  const elmo = view.locator('p').filter({ hasText: /The feature-based approach, such as ELMo/ });
  await elmo.getByRole('link', { name: /Peters/ }).click();
  await expect(result).toHaveCount(0);
  await expect(page.locator('.selected-citation-text')).toContainText('ELMo');
  await page.getByRole('button', { name: 'Analyze selection', exact: true }).click();
  await expect(result).toContainText('Deep contextualized word representations');
  await expect(result.locator('blockquote')).toContainText('deep bidirectional language model');
  await expect(result.locator('blockquote')).not.toContainText('crowdworkers');
});

test('a grouped author-year citation requires a source choice and missing source text stays unjudged', async ({ page }) => {
  await page.goto('/verify/example');
  const view = page.locator('.markdown-view');
  const grouped = view.locator('p').filter({ hasText: /^ELMo and its predecessor/ });
  await grouped.getByRole('link', { name: /2017, 2018a/ }).click();
  const choose = page.getByRole('combobox', { name: 'Cited source', exact: true });
  await expect(choose).toBeVisible();
  await expect(page.getByRole('button', { name: 'Analyze selection', exact: true })).toBeDisabled();
  await choose.selectOption({ label: await choose.locator('option').filter({ hasText: 'Deep contextualized word representations' }).innerText() });
  await page.getByRole('button', { name: 'Analyze selection', exact: true }).click();
  const result = page.getByRole('region', { name: 'Citation comparison result' });
  await expect(result).toContainText('Deep contextualized word representations');
  await view.getByRole('link', { name: /Radford et al/ }).first().click();
  await expect(result).toHaveCount(0);
  await page.getByRole('button', { name: 'Analyze selection', exact: true }).click();
  await expect(result).toContainText('Not judged');
  await expect(result).toContainText('Add the source PDF');
  await expect(result.locator('blockquote')).toHaveCount(0);
});

test('the full bibliography supports status filtering, search and detailed field checks', async ({ page }) => {
  await page.goto('/audit/example');
  await page.getByRole('button', { name: 'Run audit', exact: true }).click();
  await expect(page.locator('.audit-summary')).toContainText('56 references checked');
  const filters = page.getByRole('group', { name: 'Filter by result status' });
  for (const [name, count] of [['Metadata mismatch', 3], ['Needs review', 2], ['Not found', 1], ['Lookup failed', 2]]) {
    await filters.getByRole('button', { name: new RegExp('^' + name) }).click();
    await expect(page.locator('.finding-card')).toHaveCount(count);
    await page.locator('.finding-card').first().click();
    await expect(page.locator('.audit-detail-panel header')).toContainText(name);
  }
  await page.getByRole('button', { name: /^All references/ }).click();
  await page.getByRole('textbox', { name: 'Search references', exact: true }).fill('Universal language model');
  await expect(page.locator('.finding-card')).toHaveCount(1);
  await page.locator('.finding-card').click();
  await expect(page.locator('.audit-detail-panel')).toContainText('Input: 2019');
  await expect(page.locator('.audit-detail-panel')).toContainText('Source: 2018');
  await expect(page.locator('.audit-detail-panel').getByRole('link', { name: 'Open source record' })).toHaveAttribute('href', 'https://aclanthology.org/P18-1031/');
});
