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
    label: "Pending verification",
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

async function syncClaims(findings, localPapers, knownSourcePapers, requestId, review) {
  try {
    if (requestId !== latestClaimsRequest) return;
   const stored = await chrome.storage.local.get([
  "claimtraceBibVerification",
  "claimtraceSourcePapers"
]);

if (requestId !== latestClaimsRequest) return;

let sourcePapers = [];

try {
  // Always ask backend for the latest uploaded papers.
  const backendPapers = await loadBackendPapers();

  sourcePapers = completedPdfPapers(backendPapers);

  // Refresh the cache as well.
  await chrome.storage.local.set({
    claimtraceSourcePapers: sourcePapers,
  });

  console.log(
    "[ClaimTrace] Fresh backend source papers:",
    sourcePapers.map((paper) => ({
      paperId: paper.paper_id,
      title: paper.title,
      filename: paper.original_filename,
      status: paper.status,
    }))
  );
} catch (error) {
  if (review) throw new Error("Unable to refresh uploaded PDFs; retry manual review when the backend is available");
  console.warn(
    "[ClaimTrace] Could not refresh backend papers, using cached papers",
    error
  );

  const fallbackPapers =
    Array.isArray(knownSourcePapers) && knownSourcePapers.length
      ? knownSourcePapers
      : Array.isArray(stored.claimtraceSourcePapers)
        ? stored.claimtraceSourcePapers
        : [];

  sourcePapers = completedPdfPapers(fallbackPapers);
}
    const verificationByKey = new Map(
      (stored.claimtraceBibVerification?.results || []).map((result) => [result.citation_key, result]),
    );
    const syncedFindings = await Promise.all(findings.map(async (finding) => {
      const resolution = sourceResolution(finding.citationKey, localPapers, sourcePapers);
      const reviewedCandidate = review?.findingId === finding.id && review.claim === finding.claim
        ? resolution.candidates.find((candidate) => candidate.paperId === review.paperId && !candidate.conflict)
        : undefined;
      const sourcePaper = reviewedCandidate?.paper || resolution.automatic;
      finding = { ...finding, sourceCandidates: resolution.candidates.map(({ paper, ...candidate }) => candidate),
        manuallyReviewed: Boolean(reviewedCandidate) };
      if (!sourcePaper) {
        return previewFinding(finding, resolution.reason);
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
          annotation: `${reviewedCandidate ? "Manually selected PDF" : "Backend verification"} · ${matchCount} matching passage(s)`,
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

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === "review_source_candidate" && sender.url === chrome.runtime.getURL("src/sidepanel.html")) {
    const requestId = ++latestClaimsRequest;
    void (async () => {
      const stored = await chrome.storage.local.get(["claimtraceFindings", "claimtracePapers"]);
      const findings = stored.claimtraceFindings || [];
      const finding = findings.find((item) => item.id === message.findingId && item.claim === message.claim);
      if (!finding?.sourceCandidates?.some((candidate) => candidate.paperId === message.paperId && !candidate.conflict)) {
        throw new Error("Candidate changed; refresh the citation and review again");
      }
      await syncClaims(findings, stored.claimtracePapers || [], [], requestId, message);
      sendResponse({ ok: true });
    })().catch((error) => sendResponse({ error: error.message }));
    return true;
  }
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
