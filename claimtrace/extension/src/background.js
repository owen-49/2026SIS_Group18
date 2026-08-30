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

let latestBibliographyRequest = 0;
let latestClaimsRequest = 0;
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

function completedPdfPapers(papers) {
  return papers.filter((paper) => paper.file_type === "pdf" && paper.status === "completed");
}

async function hashText(value) {
  const bytes = new TextEncoder().encode(value);
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
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
    if (bibPaperId && previousBibSourceHash === bibSourceHash) {
      parsed = { paper_id: bibPaperId };
    } else {
      const existingPaperId = bibPaperId;
      parsed = await apiJson(
        existingPaperId ? `/api/parse/${encodeURIComponent(existingPaperId)}` : "/api/parse",
        { method: existingPaperId ? "PUT" : "POST", body: form },
      );
    }
    activeBibPaperId = parsed.paper_id;
    activeBibSourceHash = bibSourceHash;
    if (requestId !== latestBibliographyRequest) return;

    const backendPapers = await loadBackendPapers();
    const sourcePapers = completedPdfPapers(backendPapers);
    const verification = await apiJson("/api/verify/bib", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        bib_paper_id: parsed.paper_id,
        source_paper_ids: sourcePapers.map((paper) => paper.paper_id),
      }),
    });
    if (requestId !== latestBibliographyRequest) return;

    await chrome.storage.local.set({
      claimtraceBibPaperId: parsed.paper_id,
      claimtraceBibSourceHash: bibSourceHash,
      claimtraceBibVerification: verification,
      claimtraceSourcePapers: sourcePapers,
    });
    if (requestId !== latestBibliographyRequest) return;
    await setBackendStatus({
      connected: true,
      message: sourcePapers.length
        ? `Backend verified the bibliography against ${sourcePapers.length} uploaded PDF(s)`
        : "Backend parsed the bibliography; upload source PDFs in the audit workspace to verify claims",
    });

    const stored = await chrome.storage.local.get(["claimtraceFindings", "claimtracePapers"]);
    if (requestId === latestBibliographyRequest && Array.isArray(stored.claimtraceFindings)) {
      const claimsRequestId = ++latestClaimsRequest;
      await syncClaims(
        stored.claimtraceFindings,
        stored.claimtracePapers || [],
        sourcePapers,
        claimsRequestId,
      );
    }
  } catch (error) {
    if (requestId !== latestBibliographyRequest) return;
    await setBackendStatus({
      connected: false,
      message: error instanceof Error ? error.message : "Backend verification is unavailable",
    });
  }
}

async function syncClaims(findings, localPapers, knownSourcePapers, requestId) {
  try {
    if (requestId !== latestClaimsRequest) return;
    const stored = await chrome.storage.local.get(["claimtraceBibVerification", "claimtraceSourcePapers"]);
    if (requestId !== latestClaimsRequest) return;
    const sourcePapers = completedPdfPapers(knownSourcePapers || stored.claimtraceSourcePapers || []);
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

    if (requestId !== latestClaimsRequest) return;
    await chrome.storage.local.set({
      claimtraceFindings: syncedFindings,
      claimtraceCitationUpdatedAt: Date.now(),
    });
    if (requestId !== latestClaimsRequest) return;
    await setBackendStatus({
      connected: true,
      message: syncedFindings.some((finding) => !finding.preview)
        ? "Backend verification is active for matched source PDFs"
        : "Backend is connected; unmatched citations remain local previews",
    });
  } catch (error) {
    if (requestId !== latestClaimsRequest) return;
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
      const requestId = ++latestBibliographyRequest;
      bibliographySyncChain = bibliographySyncChain
        .catch(() => undefined)
        .then(() => syncBibliography(message.bibSource, requestId));
      void bibliographySyncChain;
    }
  }

  if (message.type === "citations_detected" && Array.isArray(message.findings)) {
    const requestId = ++latestClaimsRequest;
    void chrome.storage.local.set({
      claimtraceFindings: message.findings,
      claimtraceCitationSource: "overleaf",
      claimtraceCitationUpdatedAt: Date.now(),
    });
    void chrome.storage.local.get(["claimtracePapers", "claimtraceSourcePapers"])
      .then((stored) => syncClaims(
        message.findings,
        stored.claimtracePapers || [],
        stored.claimtraceSourcePapers || [],
        requestId,
      ));
  }

  if (message.type === "open_side_panel" && sender.tab?.id) {
    void chrome.sidePanel.open({ tabId: sender.tab.id });
  }
});
