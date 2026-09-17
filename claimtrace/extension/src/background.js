const API_BASE_URL = "http://localhost:8000";

const DEMO_PAPERS = [
  { citationKey: "vaswani2017attention", title: "Attention Is All You Need", authors: "Vaswani et al.", venue: "NeurIPS", year: "2017", url: "https://arxiv.org/abs/1706.03762", status: "linked" },
  { citationKey: "devlin2019bert", title: "BERT: Pre-training of Deep Bidirectional Transformers", authors: "Devlin et al.", venue: "NAACL", year: "2019", url: "https://aclanthology.org/N19-1423", status: "linked" },
  { citationKey: "brown2020language", title: "Language Models are Few-Shot Learners", authors: "Brown et al.", venue: "NeurIPS", year: "2020", url: "https://arxiv.org/abs/2005.14165", status: "linked" },
  { citationKey: "lewis2020retrieval", title: "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks", authors: "Lewis et al.", venue: "NeurIPS", year: "2020", url: "https://arxiv.org/abs/2005.11401", status: "linked" },
];

let latestBibliographyRequest = 0;
let latestAuditRequest = 0;
let activeBibPaperId;
let activeBibSourceHash;
let bibliographySyncChain = Promise.resolve();

async function apiJson(path, options = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      Accept: "application/json",
      ...(options.headers || {}),
    },
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = payload.detail;
    const message = typeof detail === "string" ? detail : detail?.message;
    throw new Error(message || `Backend request failed (${response.status})`);
  }
  return payload;
}

async function setBackendStatus(status) {
  await chrome.storage.local.set({
    claimtraceBackendStatus: {
      ...status,
      updatedAt: Date.now(),
    },
  });
}

async function loadBackendPapers() {
  const response = await apiJson("/api/papers");
  const papers = Array.isArray(response.papers) ? response.papers : [];
  await chrome.storage.local.set({ claimtraceBackendPapers: papers });
  return papers;
}

async function hashText(value) {
  const bytes = new TextEncoder().encode(value);
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

function auditBody(inputPaperId, inputType) {
  if (!inputPaperId) throw new Error("Select an audit input first");
  if (inputType === "bib") return { bib_paper_id: inputPaperId };
  if (inputType === "pdf") return { manuscript_id: inputPaperId };
  throw new Error("Unsupported audit input type");
}

async function runAudit(inputPaperId, inputType) {
  const requestId = ++latestAuditRequest;
  await chrome.storage.local.set({
    claimtraceAudit: null,
    claimtraceAuditInput: { paperId: inputPaperId, inputType },
  });
  await setBackendStatus({ connected: true, running: true, message: `Running ${inputType.toUpperCase()} bibliography audit…` });

  try {
    const audit = await apiJson("/api/audit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(auditBody(inputPaperId, inputType)),
    });
    if (requestId !== latestAuditRequest) return null;
    if (audit.contract_version !== 2 || !Array.isArray(audit.results)) {
      throw new Error("The backend returned an incompatible audit response");
    }
    await chrome.storage.local.set({ claimtraceAudit: audit, claimtraceAuditUpdatedAt: Date.now() });
    await setBackendStatus({
      connected: true,
      running: false,
      message: `Audit complete · ${audit.total_entries} reference${audit.total_entries === 1 ? "" : "s"}`,
    });
    return audit;
  } catch (error) {
    if (requestId !== latestAuditRequest) return null;
    await chrome.storage.local.set({ claimtraceAudit: null });
    await setBackendStatus({
      connected: false,
      running: false,
      message: error instanceof Error ? error.message : "Bibliography audit is unavailable",
    });
    throw error;
  }
}

async function syncBibliography(bibSource, requestId) {
  try {
    if (requestId !== latestBibliographyRequest) return;
    const bibSourceHash = await hashText(bibSource);
    if (requestId !== latestBibliographyRequest) return;

    const storedBib = await chrome.storage.local.get(["claimtraceBibPaperId", "claimtraceBibSourceHash"]);
    if (requestId !== latestBibliographyRequest) return;

    const bibPaperId = activeBibPaperId || storedBib.claimtraceBibPaperId;
    const previousBibSourceHash = activeBibSourceHash || storedBib.claimtraceBibSourceHash;
    let parsed = { paper_id: bibPaperId };
    if (bibPaperId && previousBibSourceHash === bibSourceHash) {
      parsed = { paper_id: bibPaperId };
    } else {
      const form = new FormData();
      form.append("file", new Blob([bibSource], { type: "text/plain" }), "overleaf-references.bib");
      const existingPaperId = bibPaperId;
      parsed = await apiJson(
        existingPaperId ? `/api/parse/${encodeURIComponent(existingPaperId)}` : "/api/parse",
        { method: existingPaperId ? "PUT" : "POST", body: form },
      );
    }
    activeBibPaperId = parsed.paper_id;
    activeBibSourceHash = bibSourceHash;
    if (requestId !== latestBibliographyRequest) return;

    await chrome.storage.local.set({
      claimtraceBibPaperId: parsed.paper_id,
      claimtraceBibSourceHash: bibSourceHash,
    });
    if (requestId !== latestBibliographyRequest) return;
    await runAudit(parsed.paper_id, "bib");
  } catch (error) {
    if (requestId !== latestBibliographyRequest) return;
    await chrome.storage.local.set({ claimtraceAudit: null });
    await setBackendStatus({
      connected: false,
      running: false,
      message: error instanceof Error ? error.message : "Bibliography audit is unavailable",
    });
  }
}

chrome.runtime.onInstalled.addListener(async () => {
  await chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true });
  const stored = await chrome.storage.local.get("claimtracePapers");
  if (!stored.claimtracePapers) {
    await chrome.storage.local.set({
      claimtracePapers: DEMO_PAPERS,
      claimtraceSource: "demo",
      claimtraceBackendStatus: { connected: false, running: false, message: "Open an Overleaf bibliography to run Audit" },
    });
  }
});

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === "bibliography_detected") {
    void chrome.storage.local.set({
      claimtracePapers: Array.isArray(message.papers) ? message.papers : [],
      claimtraceSource: "overleaf",
      claimtraceUpdatedAt: Date.now(),
    });
    if (typeof message.bibSource === "string" && message.bibSource.trim()) {
      const requestId = ++latestBibliographyRequest;
      bibliographySyncChain = bibliographySyncChain
        .catch(() => undefined)
        .then(() => syncBibliography(message.bibSource, requestId));
      void bibliographySyncChain;
    }
  }

  if (message.type === "citations_detected" && Array.isArray(message.findings)) {
    void chrome.storage.local.set({
      claimtraceFindings: message.findings,
      claimtraceCitationSource: "overleaf",
      claimtraceCitationUpdatedAt: Date.now(),
    });
  }

  if (message.type === "refresh_backend_papers") {
    void loadBackendPapers()
      .then((papers) => sendResponse({ ok: true, papers }))
      .catch((error) => sendResponse({ error: error.message || "Unable to load uploaded papers" }));
    return true;
  }

  if (message.type === "run_pdf_audit") {
    void (async () => {
      const papers = await loadBackendPapers();
      const selected = papers.find((paper) => paper.paper_id === message.manuscriptId);
      if (!selected || selected.file_type !== "pdf" || selected.status !== "completed") {
        throw new Error("The selected manuscript PDF is no longer available");
      }
      const audit = await runAudit(selected.paper_id, "pdf");
      sendResponse({ ok: true, audit });
    })().catch((error) => sendResponse({ error: error.message || "Unable to audit the manuscript" }));
    return true;
  }

  if (message.type === "open_side_panel" && sender.tab?.id) {
    void chrome.sidePanel.open({ tabId: sender.tab.id });
  }
});
