const paperList = document.getElementById("paperList");
const emptyState = document.getElementById("emptyState");
const paperCount = document.getElementById("paperCount");
const searchInput = document.getElementById("searchInput");
const sourceTitle = document.getElementById("sourceTitle");
const syncText = document.getElementById("syncText");
const footerDetail = document.getElementById("footerDetail");
const syncButton = document.getElementById("syncButton");

let papers = [];

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

function renderPapers() {
  const query = searchInput.value.trim().toLowerCase();
  const visible = papers.filter((paper) =>
    [paper.title, paper.authors, paper.venue, paper.year, paper.citationKey]
      .some((value) => String(value || "").toLowerCase().includes(query)),
  );

  paperCount.textContent = String(visible.length);
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

async function loadLibrary() {
  const stored = await chrome.storage.local.get(["claimtracePapers", "claimtraceSource", "claimtraceUpdatedAt"]);
  papers = Array.isArray(stored.claimtracePapers) ? stored.claimtracePapers : [];
  const isOverleaf = stored.claimtraceSource === "overleaf";
  sourceTitle.textContent = isOverleaf ? "Overleaf bibliography" : "Demo bibliography";
  syncText.textContent = isOverleaf ? "Connected to references.bib" : "Previewing the extension flow";
  footerDetail.textContent = `${papers.length} sources ready to trace`;
  renderPapers();
}

searchInput.addEventListener("input", renderPapers);
syncButton.addEventListener("click", async () => {
  syncButton.classList.add("syncing");
  await loadLibrary();
  window.setTimeout(() => syncButton.classList.remove("syncing"), 550);
});
document.getElementById("openDashboard").addEventListener("click", () => chrome.tabs.create({ url: "http://localhost:3000/library" }));
chrome.storage.onChanged.addListener((changes, areaName) => {
  if (areaName === "local" && changes.claimtracePapers) void loadLibrary();
});

void loadLibrary();
