import { configureAI } from './ai-helpers.mjs';
import { test, expect } from '@playwright/test';

const sentence = 'This method improves retrieval [7].';
const source = { source_paper_id: 'source-pdf', citation_key: 'ref7', title: 'Retrieved source', authors: ['A. Author'], venue: 'Journal', year: 2024, doi: null, url: null, database: 'local' };
const document = { total_pages: 1, pages: [{ page: 1, heading: 'Source text', paragraphs: ['Preserved source document.'] }], matched_location: { page: 1, paragraph_index: 0 } };
const evidence = [{ passage_text: 'Preserved retrieved evidence.', page: 1, similarity: 0.7, rank: 0, location: { page: 1, paragraph_index: 0 } }];
const judgement = { verdict: 'SUPPORT', confidence: 0.8, rationale: 'Comparison completed.' };
const paper = (id, type) => ({ paper_id: id, file_type: type, original_filename: `${id}.${type}`, title: id, file_size: 100, status: 'completed', pages: 1, paragraph_count: 1, entry_count: 1, error_message: null, created_at: '', updated_at: '' });
const resultFor = (status, overrides = {}) => ({ claim: sentence, claim_id: 'claim-7', citation_marker: '[7]', citation_key: 'ref7', status, message: `Message: ${status}`, cited_source: source, source_paper_id: 'source-pdf', source_document: document, evidence, judgement: status === 'COMPARED' ? judgement : null, ...overrides });

async function setup(page, { marker = '[7]', response = resultFor('COMPARED'), claimsOverride, verifySources = [], configured = true } = {}) {
  const requests = [];
  const discoveries = [];
  await page.route('**/api/papers', route => route.fulfill({ json: { total: 4, papers: [paper('manuscript', 'pdf'), paper('second', 'pdf'), paper('bib-a', 'bib'), paper('bib-b', 'bib')] } }));
  await page.route('**/api/papers/*/claims*', route => {
    discoveries.push(route.request().url());
    const claims = claimsOverride || [{ claim_id: 'claim-7', text: sentence.replace('[7]', marker), page: 1, citation_marker: marker, resolution_status: 'not_found', resolution_message: 'Source will be resolved on submission.', cited_source: null, source_document: null, similar_sources: [], manuscript_location: { page: 1, paragraph_index: 0 } }];
    return route.fulfill({ json: { manuscript_id: 'manuscript', status: 'completed', claims, error_message: null, manuscript_document: { total_pages: 1, pages: [{ page: 1, heading: 'Manuscript', paragraphs: [sentence.replace('[7]', marker), 'Unrelated paragraph.'] }], matched_location: null } } });
  });
  await page.route('**/api/verify/sources', route => route.fulfill({ json: { total: verifySources.length, papers: verifySources } }));
  await page.route('**/api/verify', () => { throw new Error('Legacy Verify must not be called'); });
  await page.route('**/api/verify/citation', async route => {
    requests.push(route.request().postDataJSON());
    await route.fulfill({ json: response });
  });
  await page.goto('/verify');
  if (configured) await configureAI(page);
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


test('changing manuscript must not carry the previous manual source', async ({page}) => {
  const sourcePdf = { ...paper('manual-source', 'pdf'), scope: 'verify_source' };
  const {requests} = await setup(page, {verifySources:[sourcePdf]});
  await highlight(page);
  await page.getByLabel('Source PDF for claim',{exact:true}).selectOption('manual-source');
  await page.getByRole('combobox',{name:'Manuscript PDF',exact:true}).selectOption('second');
  await page.locator('[data-selectable-paragraph]').first().waitFor();
  await highlight(page);
  await analyze(page).click();
  await expect(output(page)).toBeVisible();
  expect(requests.at(-1).manuscript_id).toBe('second');
  expect(requests.at(-1)).not.toHaveProperty('source_paper_id');
});

test('changing the reference in a grouped citation must reset the manual source', async ({page}) => {
  const sourcePdf = { ...paper('manual-source','pdf'),scope:'verify_source' };
  const {requests}=await setup(page,{marker:'[7,8]',verifySources:[sourcePdf]});
  await highlight(page);
  await page.getByLabel('Reference in citation',{exact:true}).selectOption('[7]');
  await page.getByLabel('Source PDF for claim',{exact:true}).selectOption('manual-source');
  await analyze(page).click();
  await expect(output(page)).toBeVisible();
  await page.getByLabel('Reference in citation',{exact:true}).selectOption('[8]');
  await analyze(page).click();
  await expect.poll(()=>requests.length).toBe(2);
  expect(requests[0].source_paper_id).toBe('manual-source');
  expect(requests[1].citation_marker).toBe('[8]');
  expect(requests[1]).not.toHaveProperty('source_paper_id');
});

for(const status of ['MANUAL_SOURCE_NOT_FOUND','MANUAL_SOURCE_NOT_READY','MANUAL_SOURCE_INVALID']){
 test(`${status} renders safely without judgement`,async({page})=>{
  await setup(page,{response:resultFor(status,{judgement})});await highlight(page);await analyze(page).click();
  await expect(output(page)).toContainText(status.replace(/_/g,' '));
  await expect(page.locator('.verdict-badge')).toHaveCount(0);
 });
}


test('source upload uses dedicated endpoint and selects it for comparison',async({page})=>{
 const {requests}=await setup(page);await highlight(page);
 const record={...paper('uploaded-source','pdf'),original_filename:'source.pdf',title:'Different parsed title',scope:'verify_source'};
 let uploaded=false;let uploadCount=0;
 await page.route('**/api/verify/sources',route=>{
  if(route.request().method()==='POST'){
   uploadCount++;uploaded=true;
   expect(route.request().headers()['content-type']).toContain('multipart/form-data');
   return route.fulfill({json:{paper_id:record.paper_id,status:'completed',scope:'verify_source',file_type:'pdf',pages:1,paragraph_count:1,entry_count:0,title:record.title}});
  }
  return route.fulfill({json:{total:uploaded?1:0,papers:uploaded?[record]:[]}});
 });
 await page.getByRole('button',{name:'Manage source PDFs',exact:true}).click();
 await page.getByRole('button',{name:'Upload source PDF',exact:true}).click();
 const dialog=page.getByRole('dialog', {name:'Upload source PDF',exact:true});
 await dialog.locator('input[type=file]').setInputFiles({name:'source.pdf',mimeType:'application/pdf',buffer:Buffer.from('%PDF-mocked-upload-fixture')});
 await expect(dialog.getByRole('status')).toContainText('ready and selected');
 await dialog.getByRole('button',{name:'Done',exact:true}).click();
 await page.getByRole('button',{name:'Close paper manager',exact:true}).click();
 await expect(page.getByLabel('Source PDF for claim',{exact:true}).locator('option:checked')).toHaveText('source.pdf');
 await expect(page.getByLabel('Source PDF for claim',{exact:true})).toHaveValue('uploaded-source');
 await analyze(page).click();await expect(output(page)).toBeVisible();
 expect(requests.at(-1).source_paper_id).toBe('uploaded-source');
 expect(uploadCount).toBe(1);
 await expect(page.getByRole('combobox',{name:'Manuscript PDF',exact:true}).locator('option[value="uploaded-source"]')).toHaveCount(0);
});

for (const change of ['highlight', 'claim']) {
  test(`changing ${change} clears the manual source and previous result`, async ({ page }) => {
    const sourcePdf = { ...paper('manual-source', 'pdf'), scope: 'verify_source' };
    const claimsOverride = change === 'claim' ? ['claim-7', 'claim-other'].map(claim_id => ({
      claim_id, text: sentence, page: 1, citation_marker: '[7]',
      resolution_status: 'not_found', cited_source: null, source_document: null,
      similar_sources: [], manuscript_location: { page: 1, paragraph_index: 0 },
    })) : undefined;
    const { requests } = await setup(page, { verifySources: [sourcePdf], claimsOverride });
    await highlight(page);
    if (change === 'claim') await page.getByLabel('Cited source', { exact: true }).selectOption('claim-7');
    const picker = page.getByLabel('Source PDF for claim', { exact: true });
    await picker.selectOption('manual-source');
    await analyze(page).click();
    await expect(output(page)).toBeVisible();
    if (change === 'claim') {
      await page.getByLabel('Cited source', { exact: true }).selectOption('claim-other');
    } else {
      // Dragging an existing highlight moves it in Chrome; create a fresh selection.
      await page.locator('[data-selectable-paragraph]').first().evaluate(el => {
        const selection = window.getSelection();
        selection.removeAllRanges();
        const range = window.document.createRange();
        range.selectNodeContents(el);
        selection.addRange(range);
        el.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
      });
    }
    await expect(picker).toHaveValue('');
    await expect(output(page)).toHaveCount(0);
    await analyze(page).click();
    await expect.poll(() => requests.length).toBe(2);
    expect(requests[0].source_paper_id).toBe('manual-source');
    expect(requests[1]).not.toHaveProperty('source_paper_id');
    if (change === 'claim') expect(requests[1].claim_id).toBe('claim-other');
  });
}
