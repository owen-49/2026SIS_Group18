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
