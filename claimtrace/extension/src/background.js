const API_BASE_URL = "http://localhost:8000";

const DEMO_PAPERS = [
  { citationKey: "vaswani2017attention", title: "Attention Is All You Need", authors: "Vaswani et al.", venue: "NeurIPS", year: "2017", url: "https://arxiv.org/abs/1706.03762", status: "linked" },
  { citationKey: "devlin2019bert", title: "BERT: Pre-training of Deep Bidirectional Transformers", authors: "Devlin et al.", venue: "NAACL", year: "2019", url: "https://aclanthology.org/N19-1423", status: "linked" },
  { citationKey: "brown2020language", title: "Language Models are Few-Shot Learners", authors: "Brown et al.", venue: "NeurIPS", year: "2020", url: "https://arxiv.org/abs/2005.14165", status: "linked" },
  { citationKey: "lewis2020retrieval", title: "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks", authors: "Lewis et al.", venue: "NeurIPS", year: "2020", url: "https://arxiv.org/abs/2005.11401", status: "linked" },
];

let latestBibliographyRequest = 0;
let latestClaimsRequest = 0;
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
    const message = typeof detail === "string" ? detail
      : Array.isArray(detail) ? detail.map((item) => item.msg).join("; ")
      : detail?.message;
    const error = new Error(message || `Backend request failed (${response.status})`);
    error.status = response.status;
    throw error;
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

async function setAuditStatus(status) {
  await chrome.storage.local.set({
    claimtraceAuditStatus: {
      ...status,
      updatedAt: Date.now(),
    },
  });
}

async function loadBackendPapers() {
  const response = await apiJson("/api/papers");
  return Array.isArray(response.papers) ? response.papers : [];
}

function completedPdfPapers(papers) {
  return papers.filter((paper) => paper.file_type === "pdf" && paper.status === "completed");
}

async function hashText(value) {
  const bytes = new TextEncoder().encode(value);
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

function auditRequestBody(inputPaperId, inputType) {
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
  await setAuditStatus({ running: true, message: `Running ${inputType.toUpperCase()} bibliography audit…` });

  try {
    const audit = await apiJson("/api/audit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(auditRequestBody(inputPaperId, inputType)),
    });
    if (requestId !== latestAuditRequest) return null;
    if (audit.contract_version !== 2 || !Array.isArray(audit.results)) {
      throw new Error("The backend returned an incompatible audit response");
    }
    await chrome.storage.local.set({ claimtraceAudit: audit, claimtraceAuditUpdatedAt: Date.now() });
    await setAuditStatus({
      running: false,
      message: `Audit complete · ${audit.total_entries} reference${audit.total_entries === 1 ? "" : "s"}`,
    });
    return audit;
  } catch (error) {
    if (requestId !== latestAuditRequest) return null;
    await chrome.storage.local.set({ claimtraceAudit: null });
    await setAuditStatus({
      running: false,
      message: error instanceof Error ? error.message : "Bibliography audit is unavailable",
    });
    throw error;
  }
}

function normaliseTitle(value) {
  return String(value || "")
    .toLowerCase()
    .replace(/\.pdf$/i, "")
    .normalize("NFKC")
    .replace(/[^\p{L}\p{N}]+/gu, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function extractArxivId(value) {
  const text = String(value || "");

  // Examples:
  // https://arxiv.org/abs/1706.03762
  // https://arxiv.org/pdf/1706.03762
  // 1706.03762.pdf
  // 1706.03762v5.pdf
  const match = text.match(/(?:^|[^a-z0-9])((?:\d{4}\.\d{4,5}|[a-z-]+(?:\.[a-z]{2})?\/\d{7}))(?:v\d+)?(?=$|[^a-z0-9])/i);

  return match?.[1]?.toLowerCase() || "";
}

function titleSimilarity(a, b) {
  const left = normaliseTitle(a);
  const right = normaliseTitle(b);

  if (!left || !right) return 0;

  if (left === right) return 1;

  const leftWords = new Set(left.split(" ").filter(Boolean));
  const rightWords = new Set(right.split(" ").filter(Boolean));

  if (!leftWords.size || !rightWords.size) return 0;

  let common = 0;

  for (const word of leftWords) {
    if (rightWords.has(word)) common += 1;
  }

  // Dice coefficient
  return (2 * common) / (leftWords.size + rightWords.size);
}

function sourceResolution(citationKey, localPapers, sourcePapers) {
  const entries = localPapers.filter((paper) => paper.citationKey === citationKey);
  if (entries.length !== 1) return { candidates: [], reason: "Missing or duplicate bibliography key" };
  const local = entries[0];
  const idsFor = (values) => [...new Set(values.map(extractArxivId).filter(Boolean))];
  const expectedIds = idsFor([local.arxivId, local.url, local.title]);
  if (expectedIds.length > 1) return { candidates: [], reason: "Conflicting bibliography arXiv IDs" };
  const expectedId = expectedIds[0];
  const papers = [...new Map(sourcePapers.filter((p) => p.paper_id).map((p) => [p.paper_id, p])).values()];
  const candidates = papers.map((paper) => {
    const ids = idsFor([paper.arxivId, paper.url, paper.title, paper.original_filename]);
    const score = Math.max(titleSimilarity(local.title, paper.title), titleSimilarity(local.title, paper.original_filename));
    const exact = Boolean(normaliseTitle(local.title)) && normaliseTitle(local.title) === normaliseTitle(paper.title || paper.original_filename);
    const idMatch = ids.length === 1 && ids[0] === expectedId;
    const conflict = ids.length > 1 || Boolean(expectedId && ids.length && !idMatch);
    return { paper, paperId: paper.paper_id, title: paper.title || "", filename: paper.original_filename || "",
      score, exact, idMatch, conflict, arxivId: ids.join(", "),
      reason: conflict ? "Conflicting arXiv ID" : idMatch ? "Same arXiv ID" : exact ? "Exact title" : "Similar title" };
  }).filter((candidate) => candidate.idMatch || candidate.score >= 0.72)
    .sort((a, b) => Number(b.idMatch) - Number(a.idMatch) || b.score - a.score || a.paperId.localeCompare(b.paperId));
  const idMatches = candidates.filter((candidate) => candidate.idMatch && !candidate.conflict);
  let automatic;
  if (expectedId && idMatches.length === 1) automatic = idMatches[0].paper;
  if (!expectedId && candidates.length === 1 && candidates[0].exact && !candidates[0].conflict) automatic = candidates[0].paper;
  return { automatic, candidates, reason: candidates.length
    ? "Source needs review — choose a candidate PDF in the Citations panel"
    : "No uploaded PDF could be confirmed" };
}

function sourcePaperFor(citationKey, localPapers, sourcePapers) {
  return sourceResolution(citationKey, localPapers, sourcePapers).automatic;
}

function previewFinding(finding, reason) {
  return {
    ...finding,
    verdict: "PENDING",
    label: "Not checked",
    confidence: null,
    annotation: reason,
    rationale: reason,
    matches: [],
    sourcePaperId: undefined,
    bibVerification: null,
    preview: true,
    backendReason: reason,
  };
}

async function syncBibliography(bibSource, requestId) {
  try {
    if (requestId !== latestBibliographyRequest) return;
    const bibSourceHash = await hashText(bibSource);
    if (requestId !== latestBibliographyRequest) return;

    const storedBib = await chrome.storage.local.get([
      "claimtraceBibPaperId",
      "claimtraceBibSourceHash",
    ]);
    if (requestId !== latestBibliographyRequest) return;

    const bibPaperId = activeBibPaperId || storedBib.claimtraceBibPaperId;
    const previousBibSourceHash = activeBibSourceHash || storedBib.claimtraceBibSourceHash;
    const form = new FormData();
    form.append("file", new Blob([bibSource], { type: "text/plain" }), "overleaf-references.bib");
    let parsed;
    try {
      if (bibPaperId && previousBibSourceHash === bibSourceHash) {
        parsed = await apiJson(`/api/parse/${encodeURIComponent(bibPaperId)}`);
      } else {
        parsed = await apiJson(
          bibPaperId ? `/api/parse/${encodeURIComponent(bibPaperId)}` : "/api/parse",
          { method: bibPaperId ? "PUT" : "POST", body: form },
        );
      }
    } catch (error) {
      if (!bibPaperId || error.status !== 404) throw error;
      parsed = await apiJson("/api/parse", { method: "POST", body: form });
    }
    if (!parsed.paper_id || parsed.status !== "completed") {
      throw new Error("Bibliography parsing is not completed; retry after parsing finishes");
    }
    activeBibPaperId = parsed.paper_id;
    activeBibSourceHash = bibSourceHash;
    if (requestId !== latestBibliographyRequest) return;

    await chrome.storage.local.set({
      claimtraceBibPaperId: parsed.paper_id,
      claimtraceBibSourceHash: bibSourceHash,
    });

    // The extension scope is bibliography Audit only. Audit uses the
    // persisted BibTeX ID directly and must not depend on /api/papers or any
    // claim/source Verify endpoint.
    const audit = await runAudit(parsed.paper_id, "bib");
    if (requestId !== latestBibliographyRequest) return;
    await setBackendStatus({
      connected: true,
      message: audit
        ? `Bibliography Audit complete · ${audit.total_entries} reference${audit.total_entries === 1 ? "" : "s"}`
        : "Bibliography Audit was superseded by a newer request",
    });
    return audit;
  } catch (error) {
    if (requestId !== latestBibliographyRequest) return;
    await setBackendStatus({
      connected: false,
      message: error instanceof Error ? error.message : "Bibliography Audit is unavailable",
    });
    throw error;
  }
}

function auditOnlyFinding(finding) {
  return {
    ...previewFinding(
      finding,
      "The extension provides bibliography Audit only; claim Verify is not enabled here.",
    ),
    label: "Not checked",
    sourceCandidates: [],
    manuallyReviewed: false,
  };
}

async function syncClaims(findings, _localPapers, _knownSourcePapers, requestId, _review) {
  // Keep this helper local for callers that still emit citation updates, but
  // never turn citation detection into a claim Verify request. The extension
  // only owns bibliography Audit.
  if (requestId !== latestClaimsRequest) return;
  await chrome.storage.local.set({
    claimtraceFindings: findings.map(auditOnlyFinding),
    claimtraceCitationUpdatedAt: Date.now(),
  });
}

chrome.runtime.onInstalled.addListener(async () => {
  await chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true });
  const stored = await chrome.storage.local.get("claimtracePapers");
  if (!stored.claimtracePapers) {
    await chrome.storage.local.set({
      claimtracePapers: DEMO_PAPERS,
      claimtraceSource: "demo",
      claimtraceBackendStatus: { connected: false, message: "Local preview; backend has not been connected" },
    });
  }
});

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === "review_source_candidate") {
    sendResponse({ error: "Claim Verify is not part of the extension; use bibliography Audit instead." });
    return true;
  }
  if (message.type === "bibliography_detected") {
    void chrome.storage.local.set({
      claimtracePapers: Array.isArray(message.papers) ? message.papers : [],
      claimtraceSource: "overleaf",
      claimtraceBibSource: message.bibSource || "",
      claimtraceUpdatedAt: Date.now(),
    });
    if (typeof message.bibSource === "string" && message.bibSource.trim()) {
      const requestId = ++latestBibliographyRequest;
      bibliographySyncChain = bibliographySyncChain
        .catch(() => undefined)
        .then(() => syncBibliography(message.bibSource, requestId))
        .catch(() => undefined);
      void bibliographySyncChain;
    }
  }

  if (message.type === "citations_detected" && Array.isArray(message.findings)) {
    void chrome.storage.local.set({
      claimtraceFindings: message.findings.map(auditOnlyFinding),
      claimtraceCitationSource: "overleaf",
      claimtraceCitationUpdatedAt: Date.now(),
    });
  }

  if (message.type === "run_bib_audit") {
    void (async () => {
      const stored = await chrome.storage.local.get(["claimtraceBibSource"]);
      if (!stored.claimtraceBibSource?.trim()) {
        throw new Error("Open a .bib file in Overleaf first, then retry Audit");
      }
      const requestId = ++latestBibliographyRequest;
      bibliographySyncChain = bibliographySyncChain.catch(() => undefined)
        .then(() => syncBibliography(stored.claimtraceBibSource, requestId));
      await bibliographySyncChain;
      sendResponse({ ok: true });
    })().catch((error) => sendResponse({ error: error.message }));
    return true;
  }

  if (message.type === "refresh_audit_papers") {
    void loadBackendPapers()
      .then(async (papers) => {
        await chrome.storage.local.set({ claimtraceSourcePapers: papers });
        sendResponse({ ok: true, papers });
      })
      .catch(async (error) => {
        const stored = await chrome.storage.local.get(["claimtraceSourcePapers"]);
        const cached = Array.isArray(stored.claimtraceSourcePapers)
          ? stored.claimtraceSourcePapers
          : [];
        if (cached.length) {
          sendResponse({
            ok: false,
            papers: cached,
            warning: `Live paper list unavailable; using the last cached list. ${error.message || ""}`.trim(),
          });
          return;
        }
        sendResponse({ error: error.message || "Unable to load uploaded papers" });
      });
    return true;
  }

  if (message.type === "run_pdf_audit") {
    void (async () => {
      if (!message.manuscriptId) throw new Error("Select a manuscript PDF first");
      // The backend validates the ID and input type. Do not make a second
      // /api/papers request here: a stale/corrupt list must not block Audit.
      const audit = await runAudit(message.manuscriptId, "pdf");
      sendResponse({ ok: true, audit });
    })().catch((error) => sendResponse({ error: error.message || "Unable to audit the manuscript" }));
    return true;
  }

  if (message.type === "open_side_panel" && sender.tab?.id) {
    void chrome.sidePanel.open({ tabId: sender.tab.id });
  }
});
