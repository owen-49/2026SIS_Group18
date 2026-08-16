const BIB_ENTRY_START = /@(article|inproceedings|book|incollection|misc|phdthesis|mastersthesis|techreport)\s*\{/gi;

function readVisibleEditorText() {
  const selectors = [".cm-content", ".ace_content", "[contenteditable='true']", "textarea"];
  const chunks = [];
  for (const selector of selectors) {
    document.querySelectorAll(selector).forEach((element) => {
      const value = "value" in element ? element.value : element.textContent;
      if (value && value.includes("@")) chunks.push(value);
    });
  }
  return chunks.sort((a, b) => b.length - a.length)[0] || "";
}

function extractEntries(source) {
  const entries = [];
  BIB_ENTRY_START.lastIndex = 0;
  let start;
  while ((start = BIB_ENTRY_START.exec(source))) {
    let depth = 1;
    let cursor = BIB_ENTRY_START.lastIndex;
    while (cursor < source.length && depth > 0) {
      if (source[cursor] === "{") depth += 1;
      if (source[cursor] === "}") depth -= 1;
      cursor += 1;
    }
    if (depth === 0) entries.push(source.slice(start.index, cursor));
  }
  return entries;
}

function readField(entry, field) {
  const expression = new RegExp(`${field}\\s*=\\s*(?:\\{([^}]*)\\}|"([^"]*)")`, "i");
  const match = entry.match(expression);
  return (match?.[1] || match?.[2] || "").replace(/\s+/g, " ").trim();
}

function parseBibliography(source) {
  return extractEntries(source).map((entry) => {
    const citationKey = entry.match(/^@\w+\s*\{\s*([^,]+)/i)?.[1]?.trim() || "unknown";
    const authorValue = readField(entry, "author");
    const firstAuthor = authorValue.split(/\s+and\s+/i)[0]?.split(",")[0]?.trim();
    const venue = readField(entry, "journal") || readField(entry, "booktitle") || "Source";
    const doi = readField(entry, "doi");
    return {
      citationKey,
      title: readField(entry, "title").replace(/[{}]/g, "") || citationKey,
      authors: firstAuthor ? `${firstAuthor} et al.` : "Unknown authors",
      venue,
      year: readField(entry, "year") || "—",
      url: readField(entry, "url") || (doi ? `https://doi.org/${doi}` : ""),
      status: "linked",
    };
  });
}

let promptDismissed = false;
let promptTimer;

function dismissPrompt() {
  promptDismissed = true;
  window.clearTimeout(promptTimer);
  const prompt = document.getElementById("claimtrace-bib-prompt");
  if (!prompt) return;
  prompt.classList.add("claimtrace-prompt-leaving");
  window.setTimeout(() => prompt.remove(), 180);
}

function ensurePrompt() {
  if (promptDismissed || document.getElementById("claimtrace-bib-prompt")) return;
  const prompt = document.createElement("div");
  prompt.id = "claimtrace-bib-prompt";
  prompt.setAttribute("role", "status");
  prompt.innerHTML = `
    <span class="claimtrace-prompt-mark">✓</span>
    <span class="claimtrace-prompt-copy"><strong>Bibliography detected</strong><small>Turn your .bib file into a paper library</small></span>
    <button class="claimtrace-prompt-open" type="button">Open ClaimTrace</button>
    <button class="claimtrace-prompt-close" type="button" aria-label="Dismiss ClaimTrace prompt">×</button>
  `;
  prompt.querySelector(".claimtrace-prompt-open").addEventListener("click", () => {
    chrome.runtime.sendMessage({ type: "open_side_panel" });
    dismissPrompt();
  });
  prompt.querySelector(".claimtrace-prompt-close").addEventListener("click", dismissPrompt);
  document.body.appendChild(prompt);
  promptTimer = window.setTimeout(dismissPrompt, 10000);
}

let lastPayload = "";
function scanOverleaf() {
  const source = readVisibleEditorText();
  const papers = parseBibliography(source);
  const pageMentionsBib = document.body.textContent?.toLowerCase().includes(".bib");
  if (papers.length || pageMentionsBib) ensurePrompt();
  if (!papers.length) return;
  const payload = JSON.stringify(papers);
  if (payload === lastPayload) return;
  lastPayload = payload;
  chrome.runtime.sendMessage({ type: "bibliography_detected", papers });
}

let timer;
const observer = new MutationObserver(() => {
  window.clearTimeout(timer);
  timer = window.setTimeout(scanOverleaf, 500);
});

observer.observe(document.documentElement, { childList: true, subtree: true, characterData: true });
scanOverleaf();
