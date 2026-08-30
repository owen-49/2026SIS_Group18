const API_BASE_URL = "http://localhost:8000";

const DEMO_PAPERS = [
  { citationKey: "vaswani2017attention", title: "Attention Is All You Need", authors: "Vaswani et al.", venue: "NeurIPS", year: "2017", url: "https://arxiv.org/abs/1706.03762", status: "linked" },
  { citationKey: "devlin2019bert", title: "BERT: Pre-training of Deep Bidirectional Transformers", authors: "Devlin et al.", venue: "NAACL", year: "2019", url: "https://aclanthology.org/N19-1423", status: "linked" },
  { citationKey: "brown2020language", title: "Language Models are Few-Shot Learners", authors: "Brown et al.", venue: "NeurIPS", year: "2020", url: "https://arxiv.org/abs/2005.14165", status: "linked" },
  { citationKey: "lewis2020retrieval", title: "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks", authors: "Lewis et al.", venue: "NeurIPS", year: "2020", url: "https://arxiv.org/abs/2005.11401", status: "linked" },
];

const VERDICT_LABELS = {
  SUPPORT: "Supported",
  PARTIAL: "Partial",
  CONTRADICT: "Contradicted",
  NOT_FOUND: "Not found",
};

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
    throw new Error(payload.detail || `Backend request failed (${response.status})`);
  }
  return payload;
}

function normaliseTitle(value) {
  return String(value || "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
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
  return Array.isArray(response.papers) ? response.papers : [];
}

function sourcePaperFor(citationKey, localPapers, sourcePapers) {
  const localPaper = localPapers.find((paper) => paper.citationKey === citationKey);
  if (!localPaper) return undefined;
  const expectedTitle = normaliseTitle(localPaper.title);
  return sourcePapers.find((paper) => {
    const backendTitles = [paper.title, paper.original_filename?.replace(/\.pdf$/i, "")]
      .map(normaliseTitle)
      .filter(Boolean);
    return backendTitles.some((title) => title === expectedTitle);
  });
}

function previewFinding(finding, reason) {
  return {
    ...finding,
    preview: true,
    backendReason: reason,
  };
}

async function syncBibliography(bibSource) {
  try {
    const form = new FormData();
    form.append("file", new Blob([bibSource], { type: "text/plain" }), "overleaf-references.bib");
    const parsed = await apiJson("/api/parse", { method: "POST", body: form });
    const backendPapers = await loadBackendPapers();
    const sourcePapers = backendPapers.filter((paper) => paper.file_type === "pdf");
    const verification = await apiJson("/api/verify/bib", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        bib_paper_id: parsed.paper_id,
        source_paper_ids: sourcePapers.map((paper) => paper.paper_id),
      }),
    });

    await chrome.storage.local.set({
      claimtraceBibPaperId: parsed.paper_id,
      claimtraceBibVerification: verification,
      claimtraceSourcePapers: sourcePapers,
    });
    await setBackendStatus({
      connected: true,
      message: sourcePapers.length
        ? `Backend verified the bibliography against ${sourcePapers.length} uploaded PDF(s)`
        : "Backend parsed the bibliography; upload source PDFs in the audit workspace to verify claims",
    });

    const stored = await chrome.storage.local.get(["claimtraceFindings", "claimtracePapers"]);
    if (Array.isArray(stored.claimtraceFindings)) {
      await syncClaims(stored.claimtraceFindings, stored.claimtracePapers || [], sourcePapers);
    }
  } catch (error) {
    await setBackendStatus({
      connected: false,
      message: error instanceof Error ? error.message : "Backend verification is unavailable",
    });
  }
}

async function syncClaims(findings, localPapers, knownSourcePapers) {
  try {
    const stored = await chrome.storage.local.get(["claimtraceBibVerification", "claimtraceSourcePapers"]);
    const sourcePapers = knownSourcePapers || stored.claimtraceSourcePapers || [];
    const verificationByKey = new Map(
      (stored.claimtraceBibVerification?.results || []).map((result) => [result.citation_key, result]),
    );
    const syncedFindings = await Promise.all(findings.map(async (finding) => {
      const sourcePaper = sourcePaperFor(finding.citationKey, localPapers, sourcePapers);
      if (!sourcePaper) {
        return previewFinding(finding, "No uploaded PDF matched this bibliography entry");
      }

      try {
        const result = await apiJson("/api/verify", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            claim: finding.claim,
            source_paper_id: sourcePaper.paper_id,
          }),
        });
        const bibResult = verificationByKey.get(finding.citationKey);
        const matchCount = Array.isArray(result.matches) ? result.matches.length : 0;
        return {
          ...finding,
          verdict: result.verdict,
          label: VERDICT_LABELS[result.verdict] || result.verdict,
          confidence: result.confidence,
          annotation: `Backend verification · ${matchCount} matching passage(s)`,
          rationale: result.rationale,
          matches: result.matches || [],
          sourcePaperId: sourcePaper.paper_id,
          bibVerification: bibResult || null,
          preview: false,
          backendReason: undefined,
        };
      } catch (error) {
        return previewFinding(
          finding,
          error instanceof Error ? error.message : "Backend claim verification failed",
        );
      }
    }));

    await chrome.storage.local.set({
      claimtraceFindings: syncedFindings,
      claimtraceCitationUpdatedAt: Date.now(),
    });
    await setBackendStatus({
      connected: true,
      message: syncedFindings.some((finding) => !finding.preview)
        ? "Backend verification is active for matched source PDFs"
        : "Backend is connected; unmatched citations remain local previews",
    });
  } catch (error) {
    await setBackendStatus({
      connected: false,
      message: error instanceof Error ? error.message : "Backend verification is unavailable",
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
      claimtraceBackendStatus: { connected: false, message: "Local preview; backend has not been connected" },
    });
  }
});

chrome.runtime.onMessage.addListener((message, sender) => {
  if (message.type === "bibliography_detected") {
    void chrome.storage.local.set({
      claimtracePapers: Array.isArray(message.papers) ? message.papers : [],
      claimtraceSource: "overleaf",
      claimtraceUpdatedAt: Date.now(),
    });
    if (typeof message.bibSource === "string" && message.bibSource.trim()) {
      void syncBibliography(message.bibSource);
    }
  }

  if (message.type === "citations_detected" && Array.isArray(message.findings)) {
    void chrome.storage.local.set({
      claimtraceFindings: message.findings,
      claimtraceCitationSource: "overleaf",
      claimtraceCitationUpdatedAt: Date.now(),
    });
    void chrome.storage.local.get(["claimtracePapers", "claimtraceSourcePapers"])
      .then((stored) => syncClaims(message.findings, stored.claimtracePapers || [], stored.claimtraceSourcePapers || []));
  }

  if (message.type === "open_side_panel" && sender.tab?.id) {
    void chrome.sidePanel.open({ tabId: sender.tab.id });
  }
});
