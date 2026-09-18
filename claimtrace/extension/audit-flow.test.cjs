const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { webcrypto } = require("node:crypto");

const source = fs.readFileSync(path.join(__dirname, "src/background.js"), "utf8");

function jsonResponse(body, ok = true, status = 200) {
  return { ok, status, async json() { return body; } };
}

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
        getURL(value) { return `chrome-extension://test/${value}`; },
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

test("Audit request bodies use exactly one contract input field", () => {
  const { context } = createHarness(() => jsonResponse(auditResponse));
  assert.deepEqual({ ...context.auditRequestBody("bib-1", "bib") }, { bib_paper_id: "bib-1" });
  assert.deepEqual({ ...context.auditRequestBody("pdf-1", "pdf") }, { manuscript_id: "pdf-1" });
});

test("BibTeX Audit stores its result without changing Verify storage", async () => {
  const { context, storage, requests } = createHarness(() => jsonResponse(auditResponse));
  storage.claimtraceBibVerification = { preserved: true };
  await context.runAudit("bib-1", "bib");
  assert.deepEqual(JSON.parse(requests[0].options.body), { bib_paper_id: "bib-1" });
  assert.equal(storage.claimtraceAudit.audit_id, "audit-1");
  assert.deepEqual(storage.claimtraceBibVerification, { preserved: true });
});

test("a failed Audit clears only the stale Audit result", async () => {
  const { context, storage } = createHarness(() => jsonResponse({ detail: "Lookup unavailable" }, false, 503));
  storage.claimtraceAudit = auditResponse;
  storage.claimtraceFindings = [{ verdict: "SUPPORT" }];
  await assert.rejects(context.runAudit("bib-1", "bib"), /Lookup unavailable/);
  assert.equal(storage.claimtraceAudit, null);
  assert.deepEqual(storage.claimtraceFindings, [{ verdict: "SUPPORT" }]);
});

test("PDF Audit validates the current paper list and sends manuscript_id", async () => {
  const responses = [
    jsonResponse({ papers: [{ paper_id: "pdf-1", file_type: "pdf", status: "completed" }] }),
    jsonResponse({ ...auditResponse, input_paper_id: "pdf-1", input_type: "pdf" }),
  ];
  const { requests, getMessageListener } = createHarness(() => responses.shift());
  const result = await new Promise((resolve) => {
    assert.equal(getMessageListener()({ type: "run_pdf_audit", manuscriptId: "pdf-1" }, {}, resolve), true);
  });
  assert.equal(result.ok, true);
  assert.deepEqual(JSON.parse(requests[1].options.body), { manuscript_id: "pdf-1" });
});
