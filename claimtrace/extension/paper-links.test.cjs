const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");

function panelContext(sendMessage = async () => ({ papers: [] })) {
  const source = fs.readFileSync(path.join(__dirname, "src/sidepanel.js"), "utf8");
  const elements = new Map();
  const context = vm.createContext({ URL, chrome: { runtime: { sendMessage } }, document: { getElementById(id) {
    if (!elements.has(id)) elements.set(id, { value: "", classList: { toggle() {} } });
    return elements.get(id);
  } } });
  // Load the rendering functions without browser event registration/startup.
  vm.runInContext(source.slice(0, source.indexOf('searchInput.addEventListener')), context);
  return { context, elements };
}

test("Audit exposes identified and unconfirmed links but rejects unsafe URLs", () => {
  const { context, elements } = panelContext();
  vm.runInContext(`audit = { warnings: ['Partial lookup'], results: [{
    status: 'NEEDS_REVIEW', entry: {metadata: {title: 'Paper'}},
    matched_record: {url: 'https://doi.org/10.1/example'},
    candidates: [{url: 'https://example.com/paper', metadata: {title: '<Title>'}},
      {url: 'javascript:alert(1)', metadata: {title: 'Unsafe'}}]
  }] }; renderAudit();`, context);
  assert.match(elements.get("auditList").innerHTML, /https:\/\/doi.org\/10.1\/example/);
  assert.match(elements.get("auditList").innerHTML, /unconfirmed/);
  assert.match(elements.get("auditList").innerHTML, /&lt;Title&gt;/);
  assert.doesNotMatch(elements.get("auditList").innerHTML, /javascript:/);
  assert.match(elements.get("auditStatus").textContent, /Partial lookup/);
});

test("local filtering retains explicit online search when there are no local results", () => {
  const { context, elements } = panelContext();
  elements.get("searchInput").value = "new topic & methods";
  vm.runInContext('renderPapers()', context);
  assert.equal(elements.get("emptyState").hidden, false);
  assert.equal(elements.get("searchOnline").hidden, false);
  assert.equal(new URL(elements.get("searchOnline").href).searchParams.get('q'), "new topic & methods");
});

test("real publications support DOI URLs, arXiv eprints and safe fallback", () => {
  const { context } = panelContext();
  assert.equal(context.publicationLink({doi:'https://doi.org/10.1234/real.2025'}).url, 'https://doi.org/10.1234/real.2025');
  assert.equal(context.publicationLink({doi:'doi:10.1234/real.2025'}).label, 'Open paper');
  assert.equal(context.publicationLink({arxivId:'2307.12345v2'}).url, 'https://arxiv.org/abs/2307.12345v2');
  assert.equal(context.publicationLink({url:'https://publisher.example/paper'}).url, 'https://publisher.example/paper');
  assert.equal(context.publicationLink({url:'javascript:alert(1)',title:'A real title'}).label,'Find paper');
});


test("cached-list warning survives rerender and clears after successful refresh", async () => {
  let response = { papers: [], warning: "Using cached list: backend unavailable" };
  const { context, elements } = panelContext(async () => response);
  await context.refreshAuditPapers();
  vm.runInContext('renderAudit(); renderAudit()', context);
  assert.match(elements.get("auditStatus").textContent, /Using cached list/);
  response = { papers: [] };
  await context.refreshAuditPapers();
  vm.runInContext('renderAudit()', context);
  assert.doesNotMatch(elements.get("auditStatus").textContent, /Using cached list/);
});

test("parse error and paper list warning are both visible", () => {
  const { context, elements } = panelContext();
  vm.runInContext('bibSyncError = "Invalid BibTeX"; paperListWarning = "Using cached list"; renderAudit()', context);
  assert.match(elements.get("auditStatus").textContent, /Invalid BibTeX/);
  assert.match(elements.get("auditStatus").textContent, /Using cached list/);
});

test("a previous Bib parse error does not hide a subsequent PDF Audit status", () => {
  const { context, elements } = panelContext();
  vm.runInContext('bibSyncError = "Invalid BibTeX"; auditState = { message: "Audit complete · 2 references" }; renderAudit()', context);
  assert.match(elements.get("auditStatus").textContent, /Bibliography: Invalid BibTeX/);
  assert.match(elements.get("auditStatus").textContent, /Audit complete/);
});

test("reference-title search filters paper cards, Audit records and their citation locations", () => {
  const { context, elements } = panelContext();
  vm.runInContext(`
    papers = [
      {citationKey: 'bert2019', title: 'BERT: Pre-training of Deep Bidirectional Transformers', authors: 'Devlin', venue: 'NAACL', year: '2019'},
      {citationKey: 'attention2017', title: 'Attention Is All You Need', authors: 'Vaswani', venue: 'NeurIPS', year: '2017'}
    ];
    findings = [
      {id: 'bert-first', citationKey: 'bert2019', claim: 'Context improves representations.', label: 'Not checked'},
      {id: 'bert-second', citationKey: 'bert2019', claim: 'Another contextual claim.', label: 'Not checked'},
      {id: 'attention-first', citationKey: 'attention2017', claim: 'Self-attention replaces recurrence.', label: 'Not checked'}
    ];
    audit = {results: papers.map(paper => ({entry: {metadata: {title: paper.title}}, status: 'VERIFIED'}))};
  `, context);
  elements.get('searchInput').value = '  PRE training of deep  ';
  vm.runInContext('renderPapers(); renderFindings(); renderAudit()', context);
  assert.equal(elements.get('paperCount').textContent, '1');
  assert.equal(elements.get('citationCount').textContent, '2');
  assert.match(elements.get('citationList').innerHTML, /BERT: Pre-training/);
  assert.doesNotMatch(elements.get('citationList').innerHTML, /attention-first/);
  assert.match(elements.get('auditList').innerHTML, /BERT: Pre-training/);
  assert.doesNotMatch(elements.get('auditList').innerHTML, /Attention Is All You Need/);
  assert.equal(elements.get('auditEmptyState').hidden, true);
  elements.get('searchInput').value = '';
  vm.runInContext('renderPapers(); renderFindings(); renderAudit()', context);
  assert.equal(elements.get('paperCount').textContent, '2');
  assert.equal(elements.get('citationCount').textContent, '3');
  assert.match(elements.get('auditList').innerHTML, /Attention Is All You Need/);
});

test("reference search does not match a claim, author, citation key or Audit reason instead of a title", () => {
  const { context, elements } = panelContext();
  vm.runInContext(`
    papers = [{citationKey: 'metadata-token', title: 'Attention Is All You Need', authors: 'Metadata-token', venue: 'Metadata-token', year: '2017'}];
    findings = [{id: 'one', citationKey: 'metadata-token', claim: 'Metadata-token improves prediction.', label: 'Metadata-token', annotation: 'Metadata-token'}];
    audit = {results: [{entry: {metadata: {title: 'Attention Is All You Need'}}, status: 'NEEDS_REVIEW', reason: 'Metadata-token'}]};
  `, context);
  elements.get('searchInput').value = 'metadata-token';
  vm.runInContext('renderPapers(); renderFindings(); renderAudit()', context);
  assert.equal(elements.get('paperCount').textContent, '0');
  assert.equal(elements.get('citationCount').textContent, '0');
  assert.equal(elements.get('citationEmptyState').hidden, false);
  assert.equal(elements.get('auditList').hidden, true);
  assert.equal(elements.get('auditEmptyState').hidden, false);
});

test("duplicate citation keys retain every reference title as searchable text", () => {
  const { context, elements } = panelContext();
  vm.runInContext(`papers = [{citationKey: 'shared', title: 'First Paper'}, {citationKey: 'shared', title: 'Second Paper'}];
    findings = [{id: 'location', citationKey: 'shared', claim: 'The sentence cites a shared key.'}];`, context);
  elements.get('searchInput').value = 'second paper';
  vm.runInContext('renderFindings()', context);
  assert.equal(elements.get('citationCount').textContent, '1');
  assert.match(elements.get('citationList').innerHTML, /Second Paper/);
});

test("nested BibTeX title braces preserve the full reference name and do not select booktitle", () => {
  const { createDom } = require('./fake-dom.cjs');
  const dom = createDom({lines: [
    '@inproceedings{devlin2019bert,',
    ' booktitle = {Proceedings of NAACL},',
    ' title = {{BERT}: Pre-training of Deep {Bidirectional} Transformers for Language Understanding},',
    ' author = {Devlin, Jacob and Chang, Ming-Wei},',
    ' year = 2019',
    '}'
  ]});
  vm.createContext(dom);
  vm.runInContext(fs.readFileSync(path.join(__dirname, 'src/content.js'), 'utf8'), dom);
  const [paper] = dom.reports('bibliography_detected').at(-1).papers;
  assert.equal(paper.title, 'BERT: Pre-training of Deep Bidirectional Transformers for Language Understanding');
  assert.equal(paper.venue, 'Proceedings of NAACL');
  assert.equal(paper.year, '2019');
  assert.equal(paper.authorList.length, 2);
});

test("quoted multiline BibTeX titles preserve protected words and escaped quotes", () => {
  const { createDom } = require('./fake-dom.cjs');
  const dom = createDom({lines: [
    '@article{quoted,',
    ' title = "Understanding {NLP}:',
    ' A \\"quoted\\" study",',
    ' year = "2020"',
    '}'
  ]});
  vm.createContext(dom);
  vm.runInContext(fs.readFileSync(path.join(__dirname, 'src/content.js'), 'utf8'), dom);
  const [paper] = dom.reports('bibliography_detected').at(-1).papers;
  assert.equal(paper.title, 'Understanding NLP: A \\"quoted\\" study');
  assert.equal(paper.year, '2020');
});
