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

test("structured Audit errors show the backend message", async () => {
  const { context, storage } = createHarness(() => jsonResponse({ detail: { code: "INPUT_NOT_FOUND", message: "Upload is missing" } }, false, 404));
  await assert.rejects(context.runAudit("missing", "bib"), /Upload is missing/);
  assert.equal(storage.claimtraceAuditStatus.message, "Upload is missing");
});

test("Bib retry recreates a deleted upload and does not depend on Verify", async () => {
  const { context, storage, requests, getMessageListener } = createHarness((url) => {
    if (url.endsWith("/api/parse/old")) return jsonResponse({ detail: "Paper not found" }, false, 404);
    if (url.endsWith("/api/parse")) return jsonResponse({ paper_id: "new", status: "completed" });
    if (url.endsWith("/api/audit")) return jsonResponse(auditResponse);
    throw new Error(`Unexpected call: ${url}`);
  });
  storage.claimtraceBibSource = '@article{ref,title={Paper}}';
  storage.claimtraceBibPaperId = "old";
  storage.claimtraceBibSourceHash = await context.hashText(storage.claimtraceBibSource);
  const result = await new Promise((resolve) => getMessageListener()({ type: "run_bib_audit" }, {}, resolve));
  assert.equal(result.ok, true);
  assert.equal(storage.claimtraceBibPaperId, "new");
  assert.equal(requests[1].options.method, "POST");
  assert.deepEqual(JSON.parse(requests[2].options.body), { bib_paper_id: "new" });
});

test("Bib retry reports parse failures without running Audit", async () => {
  const { storage, requests, getMessageListener } = createHarness(() => jsonResponse({ detail: "Invalid BibTeX" }, false, 422));
  storage.claimtraceBibSource = "invalid";
  const result = await new Promise((resolve) => getMessageListener()({ type: "run_bib_audit" }, {}, resolve));
  assert.equal(result.error, "Invalid BibTeX");
  assert.equal(requests.length, 1);
});

test("unchanged Bib retry checks the persisted ID and avoids a duplicate upload", async () => {
  const { context, storage, requests, getMessageListener } = createHarness((url) => {
    if (url.endsWith("/api/parse/existing")) return jsonResponse({ paper_id: "existing", status: "completed" });
    return jsonResponse(auditResponse);
  });
  storage.claimtraceBibSource = '@article{ref,title={Paper}}';
  storage.claimtraceBibPaperId = "existing";
  storage.claimtraceBibSourceHash = await context.hashText(storage.claimtraceBibSource);
  const result = await new Promise((resolve) => getMessageListener()({ type: "run_bib_audit" }, {}, resolve));
  assert.equal(result.ok, true);
  assert.equal(requests.length, 2);
  assert.equal(requests[0].options.method, undefined);
});

test("Bib retry requires detected source instead of auditing demo entries", async () => {
  const { requests, getMessageListener } = createHarness(() => { throw new Error("No requests expected"); });
  const result = await new Promise((resolve) => getMessageListener()({ type: "run_bib_audit" }, {}, resolve));
  assert.match(result.error, /Open a .bib file/);
  assert.equal(requests.length, 0);
});
