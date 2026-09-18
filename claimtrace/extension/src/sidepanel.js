function publicationLink(paper = {}) {
  const safe = (value) => {
    try { const url = new URL(value); return ["https:", "http:"].includes(url.protocol) ? url.href : ""; }
    catch { return ""; }
  };
  const direct = safe(paper.url);
  if (direct) return { url: direct, label: "Open paper" };
  const doi = String(paper.doi || "").trim().replace(/^(?:https?:\/\/(?:dx\.)?doi\.org\/|doi:\s*)/i, "");
  if (/^10\.\d{4,9}\/\S+$/i.test(doi)) return { url: `https://doi.org/${doi}`, label: "Open paper" };
  const arxiv = String(paper.arxivId || paper.eprint || "").trim().replace(/^(?:https?:\/\/arxiv\.org\/(?:abs|pdf)\/|arxiv:\s*)/i, "").replace(/\.pdf$/i, "");
  if (/^(?:\d{4}\.\d{4,5}|[a-z-]+(?:\.[A-Z]{2})?\/\d{7})(?:v\d+)?$/i.test(arxiv)) return { url: `https://arxiv.org/abs/${arxiv}`, label: "Open paper" };
  return { url: `https://scholar.google.com/scholar?q=${encodeURIComponent(paper.title || paper.citationKey || "")}`, label: "Find paper" };
}

const paperList = document.getElementById("paperList");
const citationList = document.getElementById("citationList");
const emptyState = document.getElementById("emptyState");
const citationEmptyState = document.getElementById("citationEmptyState");
const paperCount = document.getElementById("paperCount");
const citationCount = document.getElementById("citationCount");
const paperTabCount = document.getElementById("paperTabCount");
const citationTabCount = document.getElementById("citationTabCount");
const searchInput = document.getElementById("searchInput");
const sourceTitle = document.getElementById("sourceTitle");
const syncText = document.getElementById("syncText");
const syncButton = document.getElementById("syncButton");
const citationsTab = document.getElementById("citationsTab");
const papersTab = document.getElementById("papersTab");
const citationsView = document.getElementById("citationsView");
const papersView = document.getElementById("papersView");
const pdfAuditControls = document.getElementById("pdfAuditControls");
const pdfSelect = document.getElementById("pdfSelect");
const auditPdfButton = document.getElementById("auditPdfButton");
const auditBibButton = document.getElementById("auditBibButton");
const searchOnline = document.getElementById("searchOnline");
const auditStatus = document.getElementById("auditStatus");
const auditList = document.getElementById("auditList");

let papers = [];
let findings = [];
let backendPapers = [];
let audit = null;
let auditState = {};
let activeView = "citations";
let viewChosen = false;

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function safeUrl(value) {
  if (!value) return "";
  try {
    const url = new URL(value);
    return ["https:", "http:"].includes(url.protocol) ? url.href : "";
  } catch {
    return "";
  }
}

function verdictClass(verdict) {
  if (verdict === "PENDING") return "pending";
  if (verdict === "SUPPORT") return "support";
  if (verdict === "PARTIAL") return "partial";
  return "danger";
}

function renderPapers() {
  const query = searchInput.value.trim().toLowerCase();
  const visible = papers.filter((paper) =>
    [paper.title, paper.authors, paper.venue, paper.year, paper.citationKey]
      .some((value) => String(value || "").toLowerCase().includes(query)),
  );

  searchOnline.hidden = !query;
  searchOnline.href = `https://scholar.google.com/scholar?q=${encodeURIComponent(searchInput.value.trim())}`;
  paperCount.textContent = String(visible.length);
  paperTabCount.textContent = String(papers.length);
  emptyState.hidden = visible.length > 0;
  paperList.hidden = visible.length === 0;
  paperList.innerHTML = visible.map((paper) => {
    const destination = publicationLink(paper);
    const link = `<a href="${escapeHtml(destination.url)}" target="_blank" rel="noreferrer">${destination.label} <span>↗</span></a>`;
    return `<article class="paper-card">
      <div class="paper-title-row"><span class="paper-dot"></span><h2 title="${escapeHtml(paper.title)}">${escapeHtml(paper.title)}</h2></div>
      <p class="paper-meta">${escapeHtml(paper.authors)} · ${escapeHtml(paper.venue)} ${escapeHtml(paper.year)}</p>
      <div class="paper-footer"><code>${escapeHtml(paper.citationKey)}</code>${link}</div>
    </article>`;
  }).join("");
}

function renderCandidates(finding) {
  if (!finding.sourceCandidates?.length) return "";
  return `<details class="source-review" ${finding.preview ? "open" : ""}>
    <summary>Review candidate PDFs (${finding.sourceCandidates.length})</summary>
    <p>Title similarity is not identity confirmation. Check the original PDF before choosing.</p>
    ${finding.sourceCandidates.map((candidate) => `<div class="source-candidate">
      <strong>${escapeHtml(candidate.title)}</strong>
      <span>${escapeHtml(candidate.filename)}</span>
      <small>Upload ID: ${escapeHtml(candidate.paperId)}</small>
      <small>${escapeHtml(candidate.reason)} · ${Math.round(candidate.score * 100)}% title similarity</small>
      <small>arXiv: ${escapeHtml(candidate.arxivId || "Unavailable")}</small>
      <button type="button" data-review-finding="${escapeHtml(finding.id)}" data-review-paper="${escapeHtml(candidate.paperId)}"
        ${candidate.conflict ? "disabled" : ""}>Choose this PDF and verify</button>
    </div>`).join("")}
  </details>`;
}

function renderFindings() {
  const query = searchInput.value.trim().toLowerCase();
  const visible = findings.filter((finding) =>
    [finding.claim, finding.citationKey, finding.label, finding.annotation]
      .some((value) => String(value || "").toLowerCase().includes(query)),
  );

  citationCount.textContent = String(visible.length);
  citationTabCount.textContent = String(findings.length);
  citationEmptyState.hidden = visible.length > 0;
  citationList.hidden = visible.length === 0;
  citationList.innerHTML = visible.map((finding) => `<button class="citation-card tone-${verdictClass(finding.verdict)}" type="button" data-location-id="${escapeHtml(finding.id)}" data-citation-key="${escapeHtml(finding.citationKey)}">
    <span class="citation-card-top"><span class="citation-verdict">${escapeHtml(finding.label)}</span><span class="citation-line">Editor location</span></span>
    <strong>${escapeHtml(finding.claim)}</strong>
    <span class="citation-card-meta"><code>\\cite{${escapeHtml(finding.citationKey)}}</code><span>Locate in editor →</span></span>
    <small>${escapeHtml(finding.annotation)} · ${finding.preview ? "local preview" : "backend verified"}</small>
  </button>${renderCandidates(finding)}`).join("");
}

const auditLabels = {
  VERIFIED: "Verified",
  METADATA_MISMATCH: "Metadata mismatch",
  NEEDS_REVIEW: "Needs review",
  NOT_FOUND: "Not found",
  LOOKUP_FAILED: "Lookup failed",
};

function auditTone(status) {
  if (status === "VERIFIED") return "support";
  if (status === "METADATA_MISMATCH" || status === "NEEDS_REVIEW") return "partial";
  return "danger";
}

function renderAudit() {
  auditBibButton.disabled = Boolean(auditState.running);
  auditStatus.textContent = [auditState.message || "No Audit has been run yet.", ...(audit?.warnings || [])].join(" · ");
  auditStatus.classList.toggle("running", Boolean(auditState.running));
  auditList.hidden = !audit?.results?.length;
  auditList.innerHTML = (audit?.results || []).map((result) => {
    const metadata = result.entry?.metadata || {};
    const title = metadata.title || metadata.key || result.entry?.entry_id || "Untitled reference";
    const differences = (result.field_checks || []).filter((field) => field.status !== "MATCH" && field.status !== "NOT_CHECKED");
    return `<article class="audit-card tone-${auditTone(result.status)}">
      <div><strong>${escapeHtml(title)}</strong><span>${escapeHtml(auditLabels[result.status] || result.status)}</span></div>
      <small>${escapeHtml(result.reason || "")}</small>
      ${safeUrl(result.matched_record?.url) ? `<p><a href="${escapeHtml(safeUrl(result.matched_record.url))}" target="_blank" rel="noreferrer">Open paper ↗</a></p>` : ""}
      ${(result.candidates || []).filter((record) => safeUrl(record.url)).map((record) => `<p><a href="${escapeHtml(safeUrl(record.url))}" target="_blank" rel="noreferrer">Review candidate: ${escapeHtml(record.metadata?.title || record.record_id)} ↗</a> (unconfirmed)</p>`).join("")}

      ${differences.length ? `<details><summary>${differences.length} field difference${differences.length === 1 ? "" : "s"}</summary>${differences.map((field) => `<p><b>${escapeHtml(field.field_name)}</b>: ${escapeHtml(field.input_value || "Missing")} → ${escapeHtml(field.source_value || "Missing")}</p>`).join("")}</details>` : ""}
    </article>`;
  }).join("");
}

function setView(view, chosen = true) {
  activeView = view;
  if (chosen) viewChosen = true;
  const showingCitations = view === "citations";
  citationsView.hidden = !showingCitations;
  papersView.hidden = showingCitations;
  citationsTab.classList.toggle("active", showingCitations);
  papersTab.classList.toggle("active", !showingCitations);
  citationsTab.setAttribute("aria-selected", String(showingCitations));
  papersTab.setAttribute("aria-selected", String(!showingCitations));
  searchInput.placeholder = showingCitations ? "Search cited claims…" : "Search papers…";
  if (chosen) searchInput.value = "";
  renderPapers();
  renderFindings();
  renderAudit();
}

async function loadWorkspace() {
  const stored = await chrome.storage.local.get([
    "claimtracePapers",
    "claimtraceSource",
    "claimtraceFindings",
    "claimtraceCitationSource",
    "claimtraceBackendStatus",
    "claimtraceAuditStatus",
    "claimtraceAudit",
    "claimtraceAuditInput",
  ]);
  papers = Array.isArray(stored.claimtracePapers) ? stored.claimtracePapers : [];
  findings = Array.isArray(stored.claimtraceFindings) ? stored.claimtraceFindings : [];
  audit = stored.claimtraceAudit || null;
  auditState = stored.claimtraceAuditStatus || {};
  const hasOverleafContent = stored.claimtraceSource === "overleaf" || stored.claimtraceCitationSource === "overleaf";
  sourceTitle.textContent = hasOverleafContent ? "Your references" : "Citation workspace";
  syncText.textContent = findings.length
    ? `${findings.length} citation${findings.length === 1 ? "" : "s"} ready to review`
    : papers.length ? `${papers.length} reference${papers.length === 1 ? "" : "s"} linked` : "Open a .tex or .bib file to begin";
  const selectedId = pdfSelect.value || (stored.claimtraceAuditInput?.inputType === "pdf" ? stored.claimtraceAuditInput.paperId : "");
  const completedPdfs = backendPapers.filter((paper) => paper.file_type === "pdf" && paper.status === "completed");
  pdfSelect.innerHTML = `<option value="">Choose a PDF…</option>${completedPdfs.map((paper) =>
    `<option value="${escapeHtml(paper.paper_id)}">${escapeHtml(paper.original_filename || paper.title || paper.paper_id)}</option>`,
  ).join("")}`;
  if (completedPdfs.some((paper) => paper.paper_id === selectedId)) pdfSelect.value = selectedId;
  pdfAuditControls.hidden = false;
  auditPdfButton.disabled = !pdfSelect.value || Boolean(auditState.running);
  if (!viewChosen) activeView = findings.length ? "citations" : "papers";
  setView(activeView, false);
}

async function locateFinding(locationId, citationKey, card) {
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab?.id) throw new Error("No active Overleaf tab");
    const response = await chrome.tabs.sendMessage(tab.id, { type: "focus_citation", locationId, citationKey });
    if (!response?.found) throw new Error("Citation is not visible in the current editor file");
    document.querySelectorAll(".citation-card.located").forEach((element) => element.classList.remove("located"));
    card.classList.add("located");
    syncText.textContent = "Citation opened in your editor";
    window.setTimeout(() => card.classList.remove("located"), 1600);
  } catch (error) {
    syncText.textContent = error instanceof Error ? error.message : "Unable to locate this citation";
  }
}

async function refreshAuditPapers() {
  const response = await chrome.runtime.sendMessage({ type: "refresh_audit_papers" });
  if (response?.error) throw new Error(response.error);
  backendPapers = Array.isArray(response?.papers) ? response.papers : [];
}

searchInput.addEventListener("input", () => activeView === "citations" ? renderFindings() : renderPapers());
citationsTab.addEventListener("click", () => setView("citations"));
papersTab.addEventListener("click", () => setView("papers"));
syncButton.addEventListener("click", async () => {
  syncButton.classList.add("syncing");
  let auditRefreshError;
  try {
    await refreshAuditPapers();
  } catch (error) {
    auditRefreshError = error.message || "Unable to refresh uploaded papers for Audit";
  } finally {
    await loadWorkspace();
    if (auditRefreshError) auditStatus.textContent = auditRefreshError;
    window.setTimeout(() => syncButton.classList.remove("syncing"), 550);
  }
});
citationList.addEventListener("click", async (event) => {
  const reviewButton = event.target.closest("[data-review-paper]");
  if (reviewButton) {
    const finding = findings.find((item) => item.id === reviewButton.dataset.reviewFinding);
    if (!finding) return;
    reviewButton.disabled = true;
    try {
      const response = await chrome.runtime.sendMessage({
        type: "review_source_candidate", findingId: finding.id, claim: finding.claim,
        paperId: reviewButton.dataset.reviewPaper,
      });
      if (response?.error) throw new Error(response.error);
      await loadWorkspace();
    } catch (error) {
      syncText.textContent = error.message || "Unable to review this source";
    } finally {
      reviewButton.disabled = false;
    }
    return;
  }
  const card = event.target.closest(".citation-card");
  if (card) void locateFinding(card.dataset.locationId, card.dataset.citationKey, card);
});
auditBibButton.addEventListener("click", async () => {
  auditBibButton.disabled = true;
  setView("papers");
  try {
    const response = await chrome.runtime.sendMessage({ type: "run_bib_audit" });
    if (response?.error) throw new Error(response.error);
    await loadWorkspace();
  } catch (error) {
    auditStatus.textContent = error.message || "Unable to retry bibliography Audit";
  } finally {
    auditBibButton.disabled = Boolean(auditState.running);
  }
});
pdfSelect.addEventListener("change", () => { auditPdfButton.disabled = !pdfSelect.value || Boolean(auditState.running); });
auditPdfButton.addEventListener("click", async () => {
  if (!pdfSelect.value) return;
  auditPdfButton.disabled = true;
  try {
    const response = await chrome.runtime.sendMessage({ type: "run_pdf_audit", manuscriptId: pdfSelect.value });
    if (response?.error) throw new Error(response.error);
    await loadWorkspace();
    setView("papers");
  } catch (error) {
    auditStatus.textContent = error.message || "Unable to audit the manuscript";
  } finally {
    auditPdfButton.disabled = !pdfSelect.value || Boolean(auditState.running);
  }
});
chrome.storage.onChanged.addListener((changes, areaName) => {
  if (areaName === "local" && (changes.claimtracePapers || changes.claimtraceFindings || changes.claimtraceBackendStatus || changes.claimtraceAuditStatus || changes.claimtraceAudit)) void loadWorkspace();
});

void refreshAuditPapers()
  .then(loadWorkspace)
  .catch(async (error) => {
    await loadWorkspace();
    auditStatus.textContent = error.message || "Unable to load backend papers";
  });
