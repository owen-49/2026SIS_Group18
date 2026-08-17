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

let papers = [];
let findings = [];
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

  paperCount.textContent = String(visible.length);
  paperTabCount.textContent = String(papers.length);
  emptyState.hidden = visible.length > 0;
  paperList.hidden = visible.length === 0;
  paperList.innerHTML = visible.map((paper) => {
    const url = safeUrl(paper.url);
    const link = url ? `<a href="${escapeHtml(url)}" target="_blank" rel="noreferrer">Open paper <span>↗</span></a>` : `<span class="no-link">No link</span>`;
    return `<article class="paper-card">
      <div class="paper-title-row"><span class="paper-dot"></span><h2 title="${escapeHtml(paper.title)}">${escapeHtml(paper.title)}</h2></div>
      <p class="paper-meta">${escapeHtml(paper.authors)} · ${escapeHtml(paper.venue)} ${escapeHtml(paper.year)}</p>
      <div class="paper-footer"><code>${escapeHtml(paper.citationKey)}</code>${link}</div>
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
  citationList.innerHTML = visible.map((finding) => `<button class="citation-card tone-${verdictClass(finding.verdict)}" type="button" data-location-id="${escapeHtml(finding.id)}" data-citation-key="${escapeHtml(finding.citationKey)}">
    <span class="citation-card-top"><span class="citation-verdict">${escapeHtml(finding.label)}</span><span class="citation-line">Editor location</span></span>
    <strong>${escapeHtml(finding.claim)}</strong>
    <span class="citation-card-meta"><code>\\cite{${escapeHtml(finding.citationKey)}}</code><span>Locate in editor →</span></span>
    <small>${escapeHtml(finding.annotation)} · local demo signal</small>
  </button>`).join("");
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
}

async function loadWorkspace() {
  const stored = await chrome.storage.local.get([
    "claimtracePapers",
    "claimtraceSource",
    "claimtraceFindings",
    "claimtraceCitationSource",
  ]);
  papers = Array.isArray(stored.claimtracePapers) ? stored.claimtracePapers : [];
  findings = Array.isArray(stored.claimtraceFindings) ? stored.claimtraceFindings : [];
  const hasOverleafContent = stored.claimtraceSource === "overleaf" || stored.claimtraceCitationSource === "overleaf";
  sourceTitle.textContent = hasOverleafContent ? "Overleaf project" : "Extension preview";
  syncText.textContent = findings.length
    ? `${findings.length} cited claims annotated in the editor`
    : papers.length ? `${papers.length} bibliography entries linked` : "Open a .tex or .bib file to begin";
  footerDetail.textContent = findings.length
    ? "Verdicts are deterministic demo signals"
    : "No backend verification is running";
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
  await loadWorkspace();
  window.setTimeout(() => syncButton.classList.remove("syncing"), 550);
});
citationList.addEventListener("click", (event) => {
  const card = event.target.closest(".citation-card");
  if (card) void locateFinding(card.dataset.locationId, card.dataset.citationKey, card);
});
document.getElementById("openDashboard").addEventListener("click", () => chrome.tabs.create({ url: "http://localhost:3000/audit" }));
chrome.storage.onChanged.addListener((changes, areaName) => {
  if (areaName === "local" && (changes.claimtracePapers || changes.claimtraceFindings)) void loadWorkspace();
});

void loadWorkspace();
