import { test, expect } from '@playwright/test';

const sentence = 'This method improves retrieval [7].';
const source = { source_paper_id: 'source-pdf', citation_key: 'ref7', title: 'Retrieved source', authors: ['A. Author'], venue: 'Journal', year: 2024, doi: null, url: null, database: 'local' };
const document = { total_pages: 1, pages: [{ page: 1, heading: 'Source text', paragraphs: ['Preserved source document.'] }], matched_location: { page: 1, paragraph_index: 0 } };
const evidence = [{ passage_text: 'Preserved retrieved evidence.', page: 1, similarity: 0.7, rank: 0, location: { page: 1, paragraph_index: 0 } }];
const judgement = { verdict: 'SUPPORT', confidence: 0.8, rationale: 'Comparison completed.' };
const paper = (id, type) => ({ paper_id: id, file_type: type, original_filename: `${id}.${type}`, title: id, file_size: 100, status: 'completed', pages: 1, paragraph_count: 1, entry_count: 1, error_message: null, created_at: '', updated_at: '' });
const resultFor = (status, overrides = {}) => ({ claim: sentence, claim_id: 'claim-7', citation_marker: '[7]', citation_key: 'ref7', status, message: `Message: ${status}`, cited_source: source, source_paper_id: 'source-pdf', source_document: document, evidence, judgement: status === 'COMPARED' ? judgement : null, ...overrides });

async function setup(page, { marker = '[7]', response = resultFor('COMPARED'), claimsOverride } = {}) {
  const requests = [];
  const discoveries = [];
  await page.route('**/api/papers', route => route.fulfill({ json: { total: 4, papers: [paper('manuscript', 'pdf'), paper('second', 'pdf'), paper('bib-a', 'bib'), paper('bib-b', 'bib')] } }));
  await page.route('**/api/papers/*/claims*', route => {
    discoveries.push(route.request().url());
    const claims = claimsOverride || [{ claim_id: 'claim-7', text: sentence.replace('[7]', marker), page: 1, citation_marker: marker, resolution_status: 'not_found', resolution_message: 'Source will be resolved on submission.', cited_source: null, source_document: null, similar_sources: [], manuscript_location: { page: 1, paragraph_index: 0 } }];
    return route.fulfill({ json: { manuscript_id: 'manuscript', status: 'completed', claims, error_message: null, manuscript_document: { total_pages: 1, pages: [{ page: 1, heading: 'Manuscript', paragraphs: [sentence.replace('[7]', marker), 'Unrelated paragraph.'] }], matched_location: null } } });
  });
  await page.route('**/api/verify', () => { throw new Error('Legacy Verify must not be called'); });
  await page.route('**/api/verify/citation', async route => {
    requests.push(route.request().postDataJSON());
    await route.fulfill({ json: response });
  });
  await page.goto('/verify');
  await page.locator('[data-selectable-paragraph]').first().waitFor();
  return { requests, discoveries };
}

async function highlight(page) {
  const paragraph = page.locator('[data-selectable-paragraph]').first();
  await paragraph.scrollIntoViewIfNeeded();
  const box = await paragraph.evaluate(el => {
    const range = window.document.createRange(); range.selectNodeContents(el);
    const rect = range.getBoundingClientRect();
    return { x: rect.x, y: rect.y, width: rect.width, height: rect.height };
  });
  await page.mouse.move(box.x + 1, box.y + box.height / 2);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width + 2, box.y + box.height / 2, { steps: 8 });
  await page.mouse.up();
  await expect(page.locator('.selected-citation-text blockquote')).toBeVisible();
}
const analyze = page => page.getByRole('button', { name: 'Analyze selection', exact: true });
const output = page => page.getByRole('region', { name: 'Citation comparison result' });

for (const status of ['NO_BIBLIOGRAPHY', 'MARKER_UNSUPPORTED', 'REFERENCE_NOT_FOUND', 'REFERENCE_AMBIGUOUS', 'SOURCE_NOT_AVAILABLE', 'SOURCE_EMPTY', 'LLM_FAILED', 'FUTURE_STATUS']) {
  test(`${status} preserves message/source/evidence and never renders a verdict`, async ({ page }) => {
    // A stray judgement deliberately exercises the fail-closed status boundary.
    const { requests } = await setup(page, { response: resultFor(status, { judgement: { ...judgement, verdict: 'NOT_FOUND' } }) });
    await highlight(page);
    await expect(analyze(page)).toBeEnabled(); // Missing source IDs must not block backend resolution.
    expect(requests).toHaveLength(0);
    await analyze(page).click();
    await expect(output(page)).toContainText(`Message: ${status}`);
    await expect(output(page)).toContainText('Not judged');
    await expect(output(page)).toContainText('Retrieved source');
    await expect(output(page)).toContainText('Preserved retrieved evidence.');
    await expect(page.locator('.verdict-badge')).toHaveCount(0);
    await page.getByRole('button', { name: 'Cited source', exact: true }).click();
    await expect(page.locator('#review-cited-article').getByText('Preserved source document.', { exact: false })).toBeVisible();
    expect(requests[0]).toEqual({ claim: sentence, citation_marker: '[7]', manuscript_id: 'manuscript', claim_id: 'claim-7' });
  });
}

for (const verdict of ['SUPPORT', 'PARTIAL', 'CONTRADICT', 'NOT_FOUND']) {
  test(`COMPARED renders the real ${verdict} verdict`, async ({ page }) => {
    await setup(page, { response: resultFor('COMPARED', { judgement: { ...judgement, verdict } }) });
    await highlight(page); await analyze(page).click();
    await expect(output(page).locator(`.verdict-${verdict.toLowerCase()}`)).toHaveCount(1);
    await expect(output(page)).toContainText('Comparison completed.');
  });
}

test('bibliography is passed to discovery and Verify; changing it clears the old judgement', async ({ page }) => {
  const { requests, discoveries } = await setup(page);
  await page.getByText('Reference settings', { exact: true }).click();
  await page.getByLabel('Bibliography', { exact: true }).selectOption('bib-b');
  await expect.poll(() => discoveries.at(-1)).toContain('bib_paper_id=bib-b');
  await highlight(page); await analyze(page).click();
  await expect(output(page)).toBeVisible();
  expect(requests[0].bib_paper_id).toBe('bib-b');
  await page.getByLabel('Bibliography', { exact: true }).selectOption('');
  await expect(output(page)).toHaveCount(0);
  await expect(analyze(page)).toBeDisabled();
  await expect.poll(() => new URL(discoveries.at(-1)).search).toBe('');
});

for (const marker of ['[7,8]', '[7-9]']) {
  test(`${marker} requires one reference and preserves selected text`, async ({ page }) => {
    const { requests } = await setup(page, { marker }); await highlight(page);
    await expect(analyze(page)).toBeDisabled();
    await page.getByLabel('Reference in citation', { exact: true }).selectOption('[8]');
    await analyze(page).click(); await expect(output(page)).toBeVisible();
    expect(requests[0]).toEqual({ claim: sentence.replace('[7]', marker), citation_marker: '[8]', manuscript_id: 'manuscript', claim_id: 'claim-7' });
  });
}

for (const invalid of [null, { ...judgement, verdict: 'LLM_FAILED' }]) {
  test(`invalid COMPARED judgement is rejected: ${JSON.stringify(invalid)}`, async ({ page }) => {
    await setup(page, { response: resultFor('COMPARED', { judgement: invalid }) });
    await highlight(page); await analyze(page).click();
    await expect(page.getByRole('alert')).toContainText('no valid judgement');
    await expect(page.locator('.verdict-badge')).toHaveCount(0);
  });
}

test('503 and network failure clear earlier verdicts and keep retry available', async ({ page }) => {
  await setup(page); await highlight(page); await analyze(page).click();
  await expect(page.locator('.verdict-badge')).toHaveCount(1);
  await page.route('**/api/verify/citation', route => route.fulfill({ status: 503, json: { detail: { code: 'LLM_NOT_CONFIGURED', message: 'No model configured.' } } }));
  await analyze(page).click(); await expect(page.getByRole('alert')).toContainText('No model configured.');
  await expect(page.locator('.verdict-badge')).toHaveCount(0); await expect(analyze(page)).toBeEnabled();
  await page.route('**/api/verify/citation', route => route.abort('failed'));
  await analyze(page).click(); await expect(page.getByRole('alert')).toBeVisible();
  await expect(page.locator('.verdict-badge')).toHaveCount(0); await expect(analyze(page)).toBeEnabled();
});

test('an in-flight response cannot appear after leaving and re-entering Verify', async ({ page }) => {
  await setup(page); let release; let requested;
  const started = new Promise(resolve => { requested = resolve; });
  await page.route('**/api/verify/citation', async route => {
    requested(); await new Promise(resolve => { release = resolve; });
    await route.fulfill({ json: resultFor('COMPARED') }).catch(() => {});
  });
  await highlight(page); await analyze(page).click(); await started;
  await page.getByRole('link', { name: 'Batch audit', exact: true }).click(); release();
  await page.getByRole('link', { name: 'Review claims', exact: true }).click();
  await page.locator('[data-selectable-paragraph]').first().waitFor();
  await expect(page.locator('.verdict-badge')).toHaveCount(0);
  await expect(analyze(page)).toBeDisabled();
});

test('Audit still submits PDF and BibTeX IDs using the v2 contract', async ({ page }) => {
  await setup(page); const requests = [];
  await page.route('**/api/audit', route => { requests.push(route.request().postDataJSON()); return route.fulfill({ json: { contract_version: 2, audit_id: 'a', input_paper_id: 'manuscript', input_type: 'pdf', status: 'completed_with_errors', checked_at: '', total_entries: 0, counts: {}, warnings: ['Audit test warning.'], results: [] } }); });
  await page.goto('/audit');
  for (const [name, request] of [['manuscript.pdf', { manuscript_id: 'manuscript' }], ['bib-a.bib', { bib_paper_id: 'bib-a' }]]) {
    await page.getByRole('button', { name: 'Manage papers', exact: true }).click();
    await page.getByRole('button', { name: `Select ${name} for audit`, exact: true }).click();
    await page.getByRole('button', { name: 'Run audit', exact: true }).click();
    await expect(page.getByText('Audit test warning.', { exact: true })).toBeVisible();
    expect(requests.at(-1)).toEqual(request);
  }
});
