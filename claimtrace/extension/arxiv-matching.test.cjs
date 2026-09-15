const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const context = vm.createContext({
  console: { info() {}, warn() {} },
  chrome: { runtime: { onInstalled: { addListener() {} }, onMessage: { addListener() {} } } },
});
vm.runInContext(fs.readFileSync(require("node:path").join(__dirname, "src/background.js"), "utf8"), context);
const entry = { citationKey: "ref", title: "Learning from language models", arxivId: "1706.03762" };
const target = { paper_id: "right", title: "Parsed title", original_filename: "1706.03762v5.pdf" };
const wrong = { paper_id: "wrong", title: entry.title, original_filename: "2005.14165.pdf" };
const match = (papers, local = entry) => context.sourcePaperFor("ref", [local], papers);

test("eprint ID outranks an exact title in either upload order", () => {
  assert.equal(match([wrong, target]), target);
  assert.equal(match([target, wrong]), target);
});
test("known ID never falls back to exact or similar titles", () => {
  assert.equal(match([wrong]), undefined);
  assert.equal(match([{ paper_id: "missing", title: entry.title }]), undefined);
});
test("duplicate uploads or versions are ambiguous; duplicate list records are not", () => {
  const duplicate = { ...target, paper_id: "copy", original_filename: "1706.03762v1.pdf" };
  assert.equal(match([target, duplicate]), undefined);
  assert.equal(match([duplicate, target]), undefined);
  assert.equal(match([target, target]), target);
});
test("URL IDs work; conflicting identifiers do not select a PDF", () => {
  assert.equal(match([target], { ...entry, arxivId: "", url: "https://arxiv.org/abs/1706.03762" }), target);
  assert.equal(match([target], { ...entry, url: "https://arxiv.org/abs/2005.14165" }), undefined);
  assert.equal(match([{ ...target, url: "https://arxiv.org/abs/2005.14165" }]), undefined);
});
test("modern and legacy IDs support versions and reject digit substrings", () => {
  assert.equal(context.extractArxivId("https://arxiv.org/pdf/1706.03762v5"), "1706.03762");
  assert.equal(context.extractArxivId("hep-th/9901001v2.pdf"), "hep-th/9901001");
  assert.equal(context.extractArxivId("11706.03762.pdf"), "");
  assert.equal(context.extractArxivId("1706.037629.pdf"), "");
});
test("entries without IDs can auto-select a sole exact title", () => {
  assert.equal(match([wrong], { ...entry, arxivId: "" }), wrong);
});

test("candidate review markup escapes filenames and disables ID conflicts", () => {
  const element = { addEventListener() {} };
  const ui = vm.createContext({
    document: { getElementById() { return element; } },
    chrome: {
      storage: { local: { get: () => new Promise(() => {}) }, onChanged: { addListener() {} } },
    },
  });
  vm.runInContext(fs.readFileSync(require("node:path").join(__dirname, "src/sidepanel.js"), "utf8"), ui);
  const html = ui.renderCandidates({
    id: 'f"1', preview: true,
    sourceCandidates: [{ paperId: "p1", title: "<script>bad</script>", filename: 'a"b.pdf',
      reason: "Conflicting arXiv ID", score: .8, conflict: true }],
  });
  assert.ok(html.includes("&lt;script&gt;"));
  assert.ok(html.includes("a&quot;b.pdf"));
  assert.ok(html.includes("disabled"));
  assert.ok(html.includes('data-review-paper="p1"'));
});
test("an unresolved match clears stale verified evidence", () => {
  const result = context.previewFinding({ verdict: "SUPPORT", sourcePaperId: "old", matches: [{}], confidence: 1 }, "ID not uniquely confirmed");
  assert.equal(result.verdict, "PENDING");
  assert.equal(result.sourcePaperId, undefined);
  assert.equal(result.matches.length, 0);
  assert.equal(result.confidence, null);
});

test("multiple fuzzy titles remain reviewable in stable order, never auto-selected", () => {
  const local = { ...entry, arxivId: "", title: "Learning from large language models" };
  const sources = [
    { paper_id: "b", title: "Learning from small language models" },
    { paper_id: "a", title: "Learning with large language models" },
  ];
  const resolve = (items) => context.sourceResolution("ref", [local], items);
  assert.equal(resolve(sources).automatic, undefined);
  assert.equal(resolve(sources).candidates.length, 2);
  assert.deepEqual(Array.from(resolve(sources).candidates, (c) => c.paperId),
    Array.from(resolve([...sources].reverse()).candidates, (c) => c.paperId));
  assert.equal(resolve([sources[0]]).automatic, undefined);
});

test("duplicate exact titles and arXiv IDs retain all review candidates", () => {
  const copies = [target, { ...target, paper_id: "copy" }];
  assert.equal(context.sourceResolution("ref", [entry], copies).candidates.length, 2);
  const titles = [wrong, { ...wrong, paper_id: "copy" }];
  assert.equal(match(titles, { ...entry, arxivId: "" }), undefined);
  assert.equal(context.sourceResolution("ref", [{ ...entry, arxivId: "" }], titles).candidates.length, 2);
});

test("ID conflicts stay visible with a conflict flag; duplicate bibliography keys cannot auto-select", () => {
  const resolution = context.sourceResolution("ref", [entry], [wrong]);
  assert.equal(resolution.candidates[0].conflict, true);
  assert.equal(context.sourceResolution("ref", [entry, entry], [target]).automatic, undefined);
});

test("ambiguous sync sends no verification; manual choice sends only the chosen PDF", async () => {
  const sources = [target, { ...target, paper_id: "copy" }].map((p) => ({ ...p, file_type: "pdf", status: "completed" }));
  const storage = {};
  const sent = [];
  const sandbox = vm.createContext({
    console: { log() {}, warn() {}, info() {} },
    chrome: {
      runtime: { onInstalled: { addListener() {} }, onMessage: { addListener() {} } },
      storage: { local: { async get() { return storage; }, async set(values) { Object.assign(storage, values); } } },
    },
    async fetch(url, options) {
      if (url.endsWith("/api/papers")) return { ok: true, json: async () => ({ papers: sources }) };
      sent.push(JSON.parse(options.body));
      return { ok: true, json: async () => ({ verdict: "SUPPORT", confidence: .8, matches: [], rationale: "Test" }) };
    },
  });
  vm.runInContext(fs.readFileSync(require("node:path").join(__dirname, "src/background.js"), "utf8"), sandbox);
  const finding = { id: "f1", citationKey: "ref", claim: "A test claim", verdict: "SUPPORT", sourcePaperId: "stale" };
  await sandbox.syncClaims([finding], [entry], [], 0);
  assert.equal(sent.length, 0);
  assert.equal(storage.claimtraceFindings[0].sourceCandidates.length, 2);
  assert.equal(storage.claimtraceFindings[0].verdict, "PENDING");
  assert.equal(storage.claimtraceFindings[0].sourcePaperId, undefined);
  await sandbox.syncClaims([finding], [entry], [], 0, { findingId: "f1", claim: finding.claim, paperId: "copy" });
  assert.equal(sent.length, 1);
  assert.equal(sent[0].source_paper_id, "copy");
  assert.equal(storage.claimtraceFindings[0].manuallyReviewed, true);
  sources.pop();
  // A removed candidate cannot be selected from stale review data.
  sources.length = 0;
  await sandbox.syncClaims([finding], [entry], [], 0, { findingId: "f1", claim: finding.claim, paperId: "copy" });
  assert.equal(sent.length, 1);
  assert.equal(storage.claimtraceFindings[0].verdict, "PENDING");
});
