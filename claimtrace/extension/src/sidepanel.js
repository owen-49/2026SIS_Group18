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
const footerDetail = document.getElementById("footerDetail");
const syncButton = document.getElementById("syncButton");
const citationsTab = document.getElementById("citationsTab");
const papersTab = document.getElementById("papersTab");
const citationsView = document.getElementById("citationsView");
const papersView = document.getElementById("papersView");
const pdfAuditControls = document.getElementById("pdfAuditControls");
const pdfSelect = document.getElementById("pdfSelect");
const auditPdfButton = document.getElementById("auditPdfButton");
const auditSummary = document.getElementById("auditSummary");
const auditList = document.getElementById("auditList");

let papers = [];
let findings = [];
let backendPapers = [];
let audit = null;
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

const statusLabels = {
  VERIFIED: "Verified",
  METADATA_MISMATCH: "Metadata mismatch",
  NEEDS_REVIEW: "Needs review",
  NOT_FOUND: "Not found",
  LOOKUP_FAILED: "Lookup failed",
};

function statusClass(status) {
  if (!status || status === "UNCHECKED") return "pending";
  if (status === "VERIFIED") return "support";
  if (status === "METADATA_MISMATCH" || status === "NEEDS_REVIEW") return "partial";
  return "danger";
}

function auditKey(result) {
  return result?.entry?.metadata?.key || result?.entry?.entry_id || "";
}

function resultForCitation(citationKey) {
  return audit?.results?.find((result) => auditKey(result) === citationKey);
}

function renderPapers() {
  const query = searchInput.value.trim().toLowerCase();
  const visible = papers.filter((paper) =>
    [paper.title, paper.authors, paper.venue, paper.year, paper.citationKey]
      .some((value) => String(value || "").toLowerCase().includes(query)),
  );

  paperCount.textContent = String(visible.length);
  paperTabCount.textContent = String(papers.length);
  emptyState.hidden = visible.length > 0;
  paperList.hidden = visible.length === 0;
  paperList.innerHTML = visible.map((paper) => {
    const result = resultForCitation(paper.citationKey);
    const url = safeUrl(paper.url);
    const link = url ? `<a href="${escapeHtml(url)}" target="_blank" rel="noreferrer">Open paper <span>↗</span></a>` : `<span class="no-link">No link</span>`;
    return `<article class="paper-card tone-${statusClass(result?.status)}">
      <div class="paper-title-row"><span class="paper-dot"></span><h2 title="${escapeHtml(paper.title)}">${escapeHtml(paper.title)}</h2><span class="audit-badge">${escapeHtml(statusLabels[result?.status] || "Not audited")}</span></div>
      <p class="paper-meta">${escapeHtml(paper.authors)} · ${escapeHtml(paper.venue)} ${escapeHtml(paper.year)}</p>
      <div class="paper-footer"><code>${escapeHtml(paper.citationKey)}</code>${link}</div>
    </article>`;
  }).join("");
}

function renderAudit() {
  auditSummary.hidden = !audit;
  auditList.hidden = !audit?.results?.length;
  if (!audit) {
    auditList.innerHTML = "";
    return;
  }
  auditSummary.innerHTML = `<strong>${escapeHtml(audit.input_type.toUpperCase())} Audit</strong><span>${audit.total_entries} references · ${escapeHtml(audit.status.replaceAll("_", " "))}</span>`;
  auditList.innerHTML = audit.results.map((result) => {
    const metadata = result.entry?.metadata || {};
    const mismatches = (result.field_checks || []).filter((field) => field.status !== "MATCH" && field.status !== "NOT_CHECKED");
    return `<article class="audit-card tone-${statusClass(result.status)}">
      <div><strong>${escapeHtml(metadata.title || auditKey(result) || "Untitled reference")}</strong><span class="audit-badge">${escapeHtml(statusLabels[result.status] || result.status)}</span></div>
      <small>${escapeHtml(result.reason || "")}</small>
      ${mismatches.length ? `<details><summary>${mismatches.length} field difference${mismatches.length === 1 ? "" : "s"}</summary>${mismatches.map((field) => `<p><b>${escapeHtml(field.field_name)}</b>: ${escapeHtml(field.input_value || "Missing")} → ${escapeHtml(field.source_value || "Missing")}</p>`).join("")}</details>` : ""}
    </article>`;
  }).join("");
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
  citationList.innerHTML = visible.map((finding) => {
    const result = resultForCitation(finding.citationKey);
    return `<button class="citation-card tone-${statusClass(result?.status)}" type="button" data-location-id="${escapeHtml(finding.id)}" data-citation-key="${escapeHtml(finding.citationKey)}">
    <span class="citation-card-top"><span class="citation-verdict">${escapeHtml(statusLabels[result?.status] || "Not audited")}</span><span class="citation-line">Editor location</span></span>
    <strong>${escapeHtml(finding.claim)}</strong>
    <span class="citation-card-meta"><code>\\cite{${escapeHtml(finding.citationKey)}}</code><span>Locate in editor →</span></span>
    <small>${escapeHtml(result?.reason || "Citation location only; Audit checks the bibliography entry, not this claim.")}</small>
  </button>`;
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
  searchInput.value = "";
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
    "claimtraceBackendPapers",
    "claimtraceAudit",
    "claimtraceAuditInput",
  ]);
  papers = Array.isArray(stored.claimtracePapers) ? stored.claimtracePapers : [];
  findings = Array.isArray(stored.claimtraceFindings) ? stored.claimtraceFindings : [];
  backendPapers = Array.isArray(stored.claimtraceBackendPapers) ? stored.claimtraceBackendPapers : [];
  audit = stored.claimtraceAudit || null;
  const backendStatus = stored.claimtraceBackendStatus || {};
  const hasOverleafContent = stored.claimtraceSource === "overleaf" || stored.claimtraceCitationSource === "overleaf";
  sourceTitle.textContent = hasOverleafContent ? "Overleaf project" : "Extension preview";
  syncText.textContent = backendStatus.running ? "Audit in progress…" : findings.length
    ? `${findings.length} citation location${findings.length === 1 ? "" : "s"} detected`
    : papers.length ? `${papers.length} bibliography entries linked` : "Open a .tex or .bib file to begin";
  footerDetail.textContent = backendStatus.message || "No bibliography audit is running";
  const completedPdfs = backendPapers.filter((paper) => paper.file_type === "pdf" && paper.status === "completed");
  const selectedId = pdfSelect.value || (stored.claimtraceAuditInput?.inputType === "pdf" ? stored.claimtraceAuditInput.paperId : "");
  pdfSelect.innerHTML = `<option value="">Select an uploaded manuscript PDF</option>${completedPdfs.map((paper) =>
    `<option value="${escapeHtml(paper.paper_id)}">${escapeHtml(paper.original_filename || paper.title || paper.paper_id)}</option>`,
  ).join("")}`;
  if (completedPdfs.some((paper) => paper.paper_id === selectedId)) pdfSelect.value = selectedId;
  pdfAuditControls.hidden = false;
  auditPdfButton.disabled = !pdfSelect.value || backendStatus.running;
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
    syncText.textContent = `Located \\cite{${citationKey}} in the editor`;
    window.setTimeout(() => card.classList.remove("located"), 1600);
  } catch (error) {
    syncText.textContent = error instanceof Error ? error.message : "Unable to locate this citation";
  }
}

searchInput.addEventListener("input", () => activeView === "citations" ? renderFindings() : renderPapers());
citationsTab.addEventListener("click", () => setView("citations"));
papersTab.addEventListener("click", () => setView("papers"));
syncButton.addEventListener("click", async () => {
  syncButton.classList.add("syncing");
  try {
    const response = await chrome.runtime.sendMessage({ type: "refresh_backend_papers" });
    if (response?.error) throw new Error(response.error);
    await loadWorkspace();
  } catch (error) {
    syncText.textContent = error.message || "Unable to refresh uploaded papers";
  } finally {
    window.setTimeout(() => syncButton.classList.remove("syncing"), 550);
  }
});
citationList.addEventListener("click", async (event) => {
  const card = event.target.closest(".citation-card");
  if (card) void locateFinding(card.dataset.locationId, card.dataset.citationKey, card);
});
pdfSelect.addEventListener("change", () => { auditPdfButton.disabled = !pdfSelect.value; });
auditPdfButton.addEventListener("click", async () => {
  if (!pdfSelect.value) return;
  auditPdfButton.disabled = true;
  syncText.textContent = "Running manuscript bibliography audit…";
  try {
    const response = await chrome.runtime.sendMessage({ type: "run_pdf_audit", manuscriptId: pdfSelect.value });
    if (response?.error) throw new Error(response.error);
    await loadWorkspace();
  } catch (error) {
    syncText.textContent = error.message || "Unable to audit the manuscript";
  } finally {
    auditPdfButton.disabled = !pdfSelect.value;
  }
});
document.getElementById("openDashboard").addEventListener("click", () => chrome.tabs.create({ url: "http://localhost:3000/audit" }));
chrome.storage.onChanged.addListener((changes, areaName) => {
  if (areaName === "local" && (changes.claimtracePapers || changes.claimtraceFindings || changes.claimtraceBackendStatus || changes.claimtraceBackendPapers || changes.claimtraceAudit)) void loadWorkspace();
});

void chrome.runtime.sendMessage({ type: "refresh_backend_papers" })
  .catch(() => undefined)
  .finally(loadWorkspace);
