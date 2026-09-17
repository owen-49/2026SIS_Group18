const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { webcrypto } = require("node:crypto");

const source = fs.readFileSync(path.join(__dirname, "src/background.js"), "utf8");

function createHarness(respond) {
  const storage = {};
  const requests = [];
  let messageListener;
  const context = vm.createContext({
    console,
    Blob,
    FormData,
    TextEncoder,
    crypto: webcrypto,
    chrome: {
      sidePanel: { async setPanelBehavior() {}, async open() {} },
      runtime: {
        onInstalled: { addListener() {} },
        onMessage: { addListener(listener) { messageListener = listener; } },
      },
      storage: {
        local: {
          async get(keys) {
            if (typeof keys === "string") return { [keys]: storage[keys] };
            return Object.fromEntries((keys || []).map((key) => [key, storage[key]]));
          },
          async set(values) { Object.assign(storage, values); },
        },
      },
    },
    async fetch(url, options = {}) {
      requests.push({ url, options });
      return respond(url, options);
    },
  });
  vm.runInContext(source, context);
  return { context, storage, requests, getMessageListener: () => messageListener };
}

function jsonResponse(body, ok = true, status = 200) {
  return { ok, status, async json() { return body; } };
}

const auditResponse = {
  contract_version: 2,
  audit_id: "audit-1",
  input_paper_id: "paper-1",
  input_type: "bib",
  status: "completed",
  total_entries: 1,
  counts: { VERIFIED: 1 },
  results: [{ entry: { entry_id: "ref", metadata: { key: "ref", title: "Paper" } }, status: "VERIFIED", reason: "Found", field_checks: [] }],
  warnings: [],
};

test("extension source contains no Verify endpoint calls", () => {
  assert.equal(source.includes("/api/verify"), false);
  assert.equal(source.includes("/api/verify/bib"), false);
});

test("Audit request bodies use exactly the contract input field", () => {
  const { context } = createHarness(() => jsonResponse(auditResponse));
  assert.deepEqual({ ...context.auditBody("bib-1", "bib") }, { bib_paper_id: "bib-1" });
  assert.deepEqual({ ...context.auditBody("pdf-1", "pdf") }, { manuscript_id: "pdf-1" });
  assert.throws(() => context.auditBody("paper-1", "docx"), /Unsupported/);
});

test("BibTeX Audit stores a compatible response and never sends source PDF IDs", async () => {
  const { context, storage, requests } = createHarness(() => jsonResponse(auditResponse));
  await context.runAudit("bib-1", "bib");
  assert.equal(requests.length, 1);
  assert.match(requests[0].url, /\/api\/audit$/);
  assert.deepEqual(JSON.parse(requests[0].options.body), { bib_paper_id: "bib-1" });
  assert.equal(storage.claimtraceAudit.audit_id, "audit-1");
  assert.equal(storage.claimtraceBackendStatus.running, false);
});

test("unchanged BibTeX reuses its parsed paper ID and reruns Audit", async () => {
  const { context, requests } = createHarness((url) => {
    if (url.endsWith("/api/parse")) return jsonResponse({ paper_id: "bib-1" });
    return jsonResponse({ ...auditResponse, input_paper_id: "bib-1" });
  });
  const bib = "@article{ref, title={Paper}, year={2025}}";
  await context.syncBibliography(bib, 0);
  await context.syncBibliography(bib, 0);
  assert.equal(requests.filter(({ url }) => url.endsWith("/api/parse")).length, 1);
  assert.equal(requests.filter(({ url }) => url.endsWith("/api/audit")).length, 2);
  for (const request of requests.filter(({ url }) => url.endsWith("/api/audit"))) {
    assert.deepEqual(JSON.parse(request.options.body), { bib_paper_id: "bib-1" });
  }
});

test("a failed Audit clears the previous result", async () => {
  const { context, storage } = createHarness(() => jsonResponse({ detail: { message: "Lookup unavailable" } }, false, 503));
  storage.claimtraceAudit = auditResponse;
  await assert.rejects(context.runAudit("bib-1", "bib"), /Lookup unavailable/);
  assert.equal(storage.claimtraceAudit, null);
  assert.equal(storage.claimtraceBackendStatus.connected, false);
});

test("PDF action refreshes the backend list and submits manuscript_id", async () => {
  const responses = [
    jsonResponse({ papers: [{ paper_id: "pdf-1", file_type: "pdf", status: "completed", original_filename: "paper.pdf" }] }),
    jsonResponse({ ...auditResponse, input_paper_id: "pdf-1", input_type: "pdf" }),
  ];
  const { requests, getMessageListener } = createHarness(() => responses.shift());
  const result = await new Promise((resolve) => {
    const asynchronous = getMessageListener()({ type: "run_pdf_audit", manuscriptId: "pdf-1" }, {}, resolve);
    assert.equal(asynchronous, true);
  });
  assert.equal(result.ok, true);
  assert.deepEqual(JSON.parse(requests[1].options.body), { manuscript_id: "pdf-1" });
});
