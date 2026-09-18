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

const BIB_ENTRY_START = /@(article|inproceedings|book|incollection|misc|phdthesis|mastersthesis|techreport)\s*\{/gi;
const CITE_PATTERN = /\\cite(?:t|p|alp|author|year|yearpar|text|num)?\*?(?:\s*\[[^\]]*\]){0,2}\s*\{([^}]+)\}/gi;
const VERDICT_PRIORITY = { CONTRADICT: 3, NOT_FOUND: 3, PARTIAL: 2, SUPPORT: 1, PENDING: 0 };
const DEMO_SOURCES = {
  vaswani2017attention: { citationKey: "vaswani2017attention", title: "Attention Is All You Need", authors: "Vaswani et al.", venue: "NeurIPS", year: "2017" },
  devlin2019bert: { citationKey: "devlin2019bert", title: "BERT: Pre-training of Deep Bidirectional Transformers", authors: "Devlin et al.", venue: "NAACL", year: "2019" },
  brown2020language: { citationKey: "brown2020language", title: "Language Models are Few-Shot Learners", authors: "Brown et al.", venue: "NeurIPS", year: "2020" },
  lewis2020retrieval: { citationKey: "lewis2020retrieval", title: "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks", authors: "Lewis et al.", venue: "NeurIPS", year: "2020" },
};

const citationLocations = new Map();
const citationLineFindings = new WeakMap();
const paperLibrary = new Map(Object.entries(DEMO_SOURCES));
const backendFindings = new Map();
let citationTargets = [];
let activeCitationTarget;
let hoverHideTimer;


function readVisibleEditorText() {
  const selectors = [".cm-content", ".ace_content", "[role='textbox'][contenteditable='true']", "textarea"];
  const chunks = [];
  for (const selector of selectors) {
    document.querySelectorAll(selector).forEach((element) => {
      const value = "value" in element ? element.value : element.textContent;
      if (value?.trim()) chunks.push(value);
    });
  }
  return chunks.sort((a, b) => b.length - a.length)[0] || "";
}

function getEditorLines() {
  for (const selector of [".cm-line", ".ace_line"]) {
    const lines = Array.from(document.querySelectorAll(selector));
    if (lines.length) return lines;
  }
  return [];
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
    const citationKey =
      entry.match(/^@\w+\s*\{\s*([^,]+)/i)?.[1]?.trim() || "unknown";

    const authorValue = readField(entry, "author");

    // New：Save the complete list of authors for backend to match the papers later.
    const authorList = authorValue
      .split(/\s+and\s+/i)
      .map((author) => author.trim())
      .filter(Boolean);

    const firstAuthor =
      authorList[0]?.split(",")[0]?.trim();

    const venue =
      readField(entry, "journal") ||
      readField(entry, "booktitle") ||
      "Source";

    // The doi has been read and now it is returned
    const doi = readField(entry, "doi");

    // new：read the common arXiv eprint in bibTex
    const arxivId = readField(entry, "eprint");

    return {
      citationKey,

      title:
        readField(entry, "title").replace(/[{}]/g, "") ||
        citationKey,

      // maintain original authors，prevent impact on side panel
      authors:
        firstAuthor
          ? `${firstAuthor} et al.`
          : "Unknown authors",

      // new
      authorList,

      venue,

      year:
        readField(entry, "year") ||
        "—",

      // new
      doi,

      // new
      arxivId,

      url:
        readField(entry, "url"),

      status: "linked",
    };
  });
}

function mergePaperLibrary(papers = []) {
  papers.forEach((paper) => {
    if (paper?.citationKey) paperLibrary.set(paper.citationKey, paper);
  });
}

function rangeForOffsets(root, start, end) {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  let cursor = 0;
  let startNode;
  let startOffset = 0;
  let endNode;
  let endOffset = 0;
  let node;

  while ((node = walker.nextNode())) {
    const nextCursor = cursor + node.data.length;
    if (!startNode && start <= nextCursor) {
      startNode = node;
      startOffset = Math.max(0, start - cursor);
    }
    if (end <= nextCursor) {
      endNode = node;
      endOffset = Math.max(0, end - cursor);
      break;
    }
    cursor = nextCursor;
  }

  if (!startNode || !endNode) return null;
  const range = document.createRange();
  range.setStart(startNode, Math.min(startOffset, startNode.data.length));
  range.setEnd(endNode, Math.min(endOffset, endNode.data.length));
  return range;
}

function cleanClaim(value) {
  return value
    .replace(new RegExp(CITE_PATTERN.source, "gi"), (_, keys) => `[${keys.split(",").map((key) => key.trim()).join(", ")}]`)
    .replace(/\\(?:textbf|textit|emph)\{([^}]*)\}/g, "$1")
    .replace(/\\[a-zA-Z]+\*?(?:\[[^\]]*\])?/g, "")
    .replace(/[{}]/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

function sentenceAroundCitation(lineText, start, end) {
  const before = lineText.slice(0, start);
  const after = lineText.slice(end);

  const previousStops = [
    before.lastIndexOf(". "),
    before.lastIndexOf("? "),
    before.lastIndexOf("! ")
  ];

  const previousStop = Math.max(...previousStops);

  const sentenceStart =
    previousStop >= 0 ? previousStop + 2 : 0;

  const nextStop =
    after.search(/[.!?](?:\s|$)/);

  const sentenceEnd =
    nextStop >= 0
      ? end + nextStop + 1
      : lineText.length;

  return cleanClaim(
    lineText.slice(sentenceStart, sentenceEnd)
  );
}

function verdictForClaim(findingId, citationKey, claim) {
  const backendFinding = backendFindings.get(findingId);
  if (backendFinding?.claim === claim && backendFinding.citationKey === citationKey) return backendFinding;
  return {
    verdict: "PENDING",
    label: "Not checked",
    confidence: null,
    annotation: "Citation detected locally",
    rationale: "The extension performs bibliography Audit only; claim Verify is not enabled here.",
    preview: true,
  };
}

function verdictTone(verdict) {
  if (verdict === "PENDING") return "pending";
  return verdict === "SUPPORT" ? "support" : verdict === "PARTIAL" ? "partial" : "danger";
}

// Keep this renderer compatible with older stored findings, but do not create
// new claim evidence in the extension: the current plugin scope is bibliography
// Audit only.
function hoverPassage(finding) {
  if (finding.preview) return undefined;
  const matches = Array.isArray(finding.matches) ? finding.matches : [];
  const index = matches.findIndex(
    (match) => typeof match?.passage_text === "string" && match.passage_text.trim(),
  );
  if (index < 0) return undefined;
  const similarity = matches[index].similarity;
  return {
    text: matches[index].passage_text.trim(),
    provenance: [
      `Passage ${index + 1} of ${matches.length}`,
      // Keep the legacy field readable without implying that this extension
      // currently produces claim evidence.
      typeof similarity === "number" ? `${Math.round(similarity * 100)}% lexical overlap` : "",
    ].filter(Boolean).join(" · "),
  };
}

// US-02 is stated as a latency ("under a second"), so the hover path carries a
// measurement a person can read on the real Overleaf. The duration covers the
// synchronous body of showCitationHover up to the layout read that positions
// the card. It excludes the compositor paint and the one animation frame the
// mousemove handler waits for, and it is the number extension/README.md tells a
// reviewer how to collect.
const HOVER_START_MARK = "claimtrace:hover:start";
const HOVER_MEASURE = "claimtrace:hover";

function markHoverStart() {
  try {
    window.performance?.mark?.(HOVER_START_MARK);
  } catch {
    // A diagnostic must not be able to break the feature it measures.
  }
}

function measureHover() {
  try {
    const duration = window.performance?.measure?.(HOVER_MEASURE, HOVER_START_MARK)?.duration;
    if (typeof duration !== "number") return;
    console.log(`[ClaimTrace] hover card in ${duration.toFixed(1)} ms`);
  } catch {
    // Same reason as markHoverStart.
  }
}

function clearEditorAnnotations() {
  document.querySelectorAll(".claimtrace-citation-line").forEach((line) => {
    line.classList.remove("claimtrace-citation-line", "claimtrace-tone-support", "claimtrace-tone-partial", "claimtrace-tone-danger", "claimtrace-tone-pending", "claimtrace-focus-line", "claimtrace-hover-line");
    delete line.dataset.claimtraceLabel;
    delete line.dataset.claimtraceLocation;
  });
  citationLocations.clear();
  citationTargets = [];
  activeCitationTarget = undefined;
  if (typeof CSS !== "undefined" && CSS.highlights) {
    CSS.highlights.delete("claimtrace-citations-support");
    CSS.highlights.delete("claimtrace-citations-partial");
    CSS.highlights.delete("claimtrace-citations-danger");
    CSS.highlights.delete("claimtrace-citations-pending");
    CSS.highlights.delete("claimtrace-citation-active");
  }
}

function getHoverCard() {
  let card = document.getElementById("claimtrace-citation-hover");
  if (card) return card;
  card = document.createElement("aside");
  card.id = "claimtrace-citation-hover";
  card.setAttribute("role", "dialog");
  card.setAttribute("aria-label", "Citation details");
  card.hidden = true;
  card.innerHTML = `
    <div class="claimtrace-hover-toolbar"><span class="claimtrace-hover-verdict"></span><button class="claimtrace-hover-close" type="button" aria-label="Close citation details">×</button></div>
    <section class="claimtrace-hover-source"><strong class="claimtrace-hover-title"></strong><small class="claimtrace-hover-meta"></small></section>
    <section class="claimtrace-hover-claim-section"><span>In your writing</span><p class="claimtrace-hover-claim"></p></section>
    <section class="claimtrace-hover-passage" hidden><span>Supporting passage</span><blockquote class="claimtrace-hover-quote"></blockquote><small class="claimtrace-hover-provenance"></small></section>
    <p class="claimtrace-hover-detail" hidden></p>
    <footer><a class="claimtrace-hover-open" target="_blank" rel="noreferrer">Open paper ↗</a><small>Esc to close</small></footer>
  `;
  card.querySelector(".claimtrace-hover-close").addEventListener("click", closeCitationHover);
  document.body.appendChild(card);
  return card;
}

function showCitationHover(target) {
  window.clearTimeout(hoverHideTimer);
  if (!target) return;
  markHoverStart();
  const { finding, line, range } = target;
  const tone = verdictTone(finding.verdict);
  const source = paperLibrary.get(finding.citationKey);
  const card = getHoverCard();
  card.hidden = false;
  card.className = `claimtrace-hover-visible claimtrace-hover-${tone}`;
  card.querySelector(".claimtrace-hover-verdict").textContent = finding.preview ? "Not checked" : finding.label;
  card.querySelector(".claimtrace-hover-claim").textContent = finding.claim;
  card.querySelector(".claimtrace-hover-title").textContent = source?.title || finding.citationKey;
  card.querySelector(".claimtrace-hover-meta").textContent = source
    ? [source.authors, source.venue, source.year].filter(Boolean).join(" · ") : "Bibliography entry unavailable";
  const detail = card.querySelector(".claimtrace-hover-detail");
  detail.textContent = finding.preview ? "" : finding.rationale;
  detail.hidden = !detail.textContent;
  const link = publicationLink(source || { citationKey: finding.citationKey });
  const open = card.querySelector(".claimtrace-hover-open");
  open.setAttribute("href", link.url);
  open.textContent = `${link.label} ↗`;
  const passage = hoverPassage(finding);
  card.querySelector(".claimtrace-hover-quote").textContent = passage?.text || "";
  card.querySelector(".claimtrace-hover-provenance").textContent = passage?.provenance || "";
  card.querySelector(".claimtrace-hover-passage").hidden = !passage;

  if (activeCitationTarget && activeCitationTarget !== target) {
    activeCitationTarget.line.classList.remove("claimtrace-hover-line");
  }
  activeCitationTarget = target;
  line.classList.add("claimtrace-hover-line");
  if (range && typeof CSS !== "undefined" && CSS.highlights && typeof Highlight !== "undefined") {
    CSS.highlights.set("claimtrace-citation-active", new Highlight(range));
  }

  const citationRect = range?.getBoundingClientRect() || line.getBoundingClientRect();
  const cardRect = card.getBoundingClientRect();
  const preferredTop = citationRect.bottom + 9;
  const top = preferredTop + cardRect.height < window.innerHeight - 12
    ? preferredTop
    : Math.max(12, citationRect.top - cardRect.height - 9);
  const left = Math.min(Math.max(12, citationRect.left), window.innerWidth - cardRect.width - 12);
  card.style.top = `${top}px`;
  card.style.left = `${left}px`;
  measureHover();
}

function closeCitationHover() {
  window.clearTimeout(hoverHideTimer);
  const card = document.getElementById("claimtrace-citation-hover");
  if (card) {
    card.classList.remove("claimtrace-hover-visible");
    card.hidden = true;
  }
  activeCitationTarget?.line.classList.remove("claimtrace-hover-line");
  activeCitationTarget = undefined;
  if (typeof CSS !== "undefined") CSS.highlights?.delete("claimtrace-citation-active");
}

document.addEventListener("pointerdown", (event) => {
  if (event.target?.closest?.("#claimtrace-citation-hover")) return;
  const target = citationTargets.find(({ range }) => Array.from(range.getClientRects()).some((rect) =>
    event.clientX >= rect.left && event.clientX <= rect.right && event.clientY >= rect.top && event.clientY <= rect.bottom));
  if (target) showCitationHover(target);
  else closeCitationHover();
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") closeCitationHover();
});

function installCitationHighlights() {
  if (typeof CSS === "undefined" || !CSS.highlights || typeof Highlight === "undefined") return;
  ["support", "partial", "danger", "pending"].forEach((tone) => {
    const ranges = citationTargets.filter((target) => target.tone === tone).map((target) => target.range);
    if (ranges.length) CSS.highlights.set(`claimtrace-citations-${tone}`, new Highlight(...ranges));
  });
}

function annotateCitationLines() {
  const openFinding = activeCitationTarget?.finding;
  clearEditorAnnotations();
  const findings = [];
  const lines = getEditorLines();

  lines.forEach((line, lineIndex) => {
    const text = line.textContent || "";
    const lineFindings = [];
    CITE_PATTERN.lastIndex = 0;
    let match;
    while ((match = CITE_PATTERN.exec(text))) {
      const claim = sentenceAroundCitation(text, match.index, CITE_PATTERN.lastIndex);
      console.log("[ClaimTrace] line text:", text);
      console.log("[ClaimTrace] citation:", match[0]);
      console.log("[ClaimTrace] match index:", match.index);
      console.log("[ClaimTrace] extracted claim:", claim);
      const range = rangeForOffsets(line, match.index, CITE_PATTERN.lastIndex);
      const keys = match[1].split(",").map((key) => key.trim()).filter(Boolean);
      keys.forEach((citationKey, keyIndex) => {
        const locationId = `${lineIndex + 1}-${match.index}-${keyIndex}-${citationKey}`;
        const preview = verdictForClaim(locationId, citationKey, claim || `Citation ${citationKey}`);
        const finding = {
          id: locationId,
          citationKey,
          claim: claim || `Citation ${citationKey}`,
          line: lineIndex + 1,
          verdict: preview.verdict,
          label: preview.label,
          confidence: preview.confidence,
          annotation: preview.annotation,
          rationale: preview.rationale,
          matches: preview.matches || [],
          sourcePaperId: preview.sourcePaperId,
          backendReason: preview.backendReason,
          preview: preview.preview !== false,
        };
        findings.push(finding);
        lineFindings.push(finding);
        const tone = verdictTone(finding.verdict);
        const target = { finding, line, range, tone };
        citationLocations.set(locationId, target);
        if (range) citationTargets.push(target);
      });
    }

    if (!lineFindings.length) return;
    const strongest = lineFindings.reduce((current, finding) =>
      VERDICT_PRIORITY[finding.verdict] > VERDICT_PRIORITY[current.verdict] ? finding : current,
    );
    const tone = verdictTone(strongest.verdict);
    line.classList.add("claimtrace-citation-line", `claimtrace-tone-${tone}`);
    line.dataset.claimtraceLabel = `ClaimTrace · local citation preview · ${strongest.label}`;
    line.dataset.claimtraceLocation = strongest.id;
    citationLineFindings.set(line, lineFindings);
  });

  installCitationHighlights();
  if (openFinding) {
    const replacement = citationLocations.get(openFinding.id);
    if (replacement && replacement.finding.claim === openFinding.claim) showCitationHover(replacement);
    else closeCitationHover();
  }
  return findings;
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

let lastPaperPayload = "";
let lastCitationPayload = "";

function scanOverleaf() {
  const source = readVisibleEditorText();
  const papers = parseBibliography(source);
  mergePaperLibrary(papers);
  const pageMentionsBib = document.body.textContent?.toLowerCase().includes(".bib");
  if (papers.length || pageMentionsBib) ensurePrompt();

  if (papers.length) {
    const payload = JSON.stringify(papers);
    if (payload !== lastPaperPayload) {
      lastPaperPayload = payload;
      chrome.runtime.sendMessage({ type: "bibliography_detected", papers, bibSource: source });
    }
  }

  const findings = annotateCitationLines();
  const looksLikeTex = /\\(?:documentclass|begin|section|cite)/.test(source) && !papers.length;
  if (findings.length || looksLikeTex) {
    const payload = JSON.stringify(findings);
    if (payload !== lastCitationPayload) {
      lastCitationPayload = payload;
      chrome.runtime.sendMessage({ type: "citations_detected", findings });
    }
  }
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message.type !== "focus_citation") return;
  const target = citationLocations.get(message.locationId)
    || Array.from(citationLocations.entries()).find(([id]) => id.endsWith(`-${message.citationKey}`))?.[1];
  if (!target) {
    sendResponse({ found: false });
    return;
  }
  const { line } = target;
  line.scrollIntoView({ behavior: "smooth", block: "center" });
  line.classList.remove("claimtrace-focus-line");
  window.requestAnimationFrame(() => line.classList.add("claimtrace-focus-line"));
  window.setTimeout(() => {
    showCitationHover(target);
    window.setTimeout(() => {
      line.classList.remove("claimtrace-focus-line");
    }, 1800);
  }, 350);
  sendResponse({ found: true });
});

let pointerFrame;
let latestPointer;
document.addEventListener("mousemove", (event) => {
  latestPointer = event;
  if (event.target?.closest?.("#claimtrace-citation-hover")) {
    window.clearTimeout(hoverHideTimer);
    return;
  }
  if (pointerFrame) return;
  pointerFrame = window.requestAnimationFrame(() => {
    pointerFrame = undefined;
    const event = latestPointer;
    if (event.target?.closest?.("#claimtrace-citation-hover")) return;
    const target = citationTargets.find(({ range }) => Array.from(range.getClientRects()).some((rect) =>
      event.clientX >= rect.left && event.clientX <= rect.right && event.clientY >= rect.top && event.clientY <= rect.bottom,
    ));
    if (target) {
      if (target !== activeCitationTarget) showCitationHover(target);
      else window.clearTimeout(hoverHideTimer);
    }
  });
});


chrome.storage.local.get(["claimtracePapers", "claimtraceFindings"], ({ claimtracePapers, claimtraceFindings }) => {
  mergePaperLibrary(claimtracePapers);
  backendFindings.clear();
  (claimtraceFindings || []).filter((finding) => finding.preview === false).forEach((finding) => {
    if (finding.id) backendFindings.set(finding.id, finding);
  });
  if (backendFindings.size) annotateCitationLines();
});
chrome.storage.onChanged.addListener((changes, areaName) => {
  if (areaName !== "local") return;
  if (changes.claimtracePapers?.newValue) mergePaperLibrary(changes.claimtracePapers.newValue);
  if (changes.claimtraceFindings?.newValue) {
    backendFindings.clear();
    (changes.claimtraceFindings.newValue || []).filter((finding) => finding.preview === false).forEach((finding) => {
      if (finding.id) backendFindings.set(finding.id, finding);
    });
    annotateCitationLines();
  }
});

function isClaimTraceMutation(mutation) {
  const target = mutation.target.nodeType === Node.ELEMENT_NODE ? mutation.target : mutation.target.parentElement;
  if (target?.closest?.("#claimtrace-citation-hover, #claimtrace-bib-prompt")) return true;
  const changedNodes = [...mutation.addedNodes, ...mutation.removedNodes];
  return changedNodes.length > 0 && changedNodes.every((node) =>
    node.nodeType === Node.ELEMENT_NODE
      && (node.matches?.("#claimtrace-citation-hover, #claimtrace-bib-prompt") || node.closest?.("#claimtrace-citation-hover, #claimtrace-bib-prompt")),
  );
}

let timer;
const observer = new MutationObserver((mutations) => {
  if (mutations.every(isClaimTraceMutation)) return;
  window.clearTimeout(timer);
  timer = window.setTimeout(scanOverleaf, 500);
});

observer.observe(document.documentElement, { childList: true, subtree: true, characterData: true });
scanOverleaf();
