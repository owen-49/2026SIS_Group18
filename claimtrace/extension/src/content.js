const BIB_ENTRY_START = /@(article|inproceedings|book|incollection|misc|phdthesis|mastersthesis|techreport)\s*\{/gi;
const CITE_PATTERN = /\\cite(?:t|p|alp|author|year|yearpar|text|num)?\*?(?:\s*\[[^\]]*\]){0,2}\s*\{([^}]+)\}/gi;
const VERDICT_PRIORITY = { CONTRADICT: 3, NOT_FOUND: 3, PARTIAL: 2, SUPPORT: 1 };
const DEMO_VERDICTS = {
  devlin2019bert: { verdict: "CONTRADICT", label: "Contradicted", confidence: 0.89, annotation: "Claim contradicts the cited source", rationale: "BERT used both masked-language modelling and next-sentence prediction during pre-training, so the word ‘exclusively’ is not supported." },
  brown2020language: { verdict: "PARTIAL", label: "Partial", confidence: 0.82, annotation: "Claim is broader than the evidence", rationale: "The cited results show gains at several scales, but do not establish that larger models always improve every few-shot task." },
  smith2024survey: { verdict: "NOT_FOUND", label: "Not found", confidence: 0.76, annotation: "Source could not be located", rationale: "No matching bibliography record or linked paper is available for this citation key." },
  vaswani2017attention: { verdict: "SUPPORT", label: "Supported", confidence: 0.94, annotation: "Claim is supported by the cited source", rationale: "The paper describes the Transformer as relying on attention mechanisms without recurrence or convolutions." },
  lewis2020retrieval: { verdict: "SUPPORT", label: "Supported", confidence: 0.91, annotation: "Claim is supported by the cited source", rationale: "The cited paper explicitly combines parametric model memory with non-parametric retrieved memory." },
};
const DEMO_SOURCES = {
  vaswani2017attention: { citationKey: "vaswani2017attention", title: "Attention Is All You Need", authors: "Vaswani et al.", venue: "NeurIPS", year: "2017" },
  devlin2019bert: { citationKey: "devlin2019bert", title: "BERT: Pre-training of Deep Bidirectional Transformers", authors: "Devlin et al.", venue: "NAACL", year: "2019" },
  brown2020language: { citationKey: "brown2020language", title: "Language Models are Few-Shot Learners", authors: "Brown et al.", venue: "NeurIPS", year: "2020" },
  lewis2020retrieval: { citationKey: "lewis2020retrieval", title: "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks", authors: "Lewis et al.", venue: "NeurIPS", year: "2020" },
};

const citationLocations = new Map();
const citationLineFindings = new WeakMap();
const paperLibrary = new Map(Object.entries(DEMO_SOURCES));
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
  const previousStops = [before.lastIndexOf(". "), before.lastIndexOf("? "), before.lastIndexOf("! ")];
  const sentenceStart = Math.max(...previousStops) + (Math.max(...previousStops) >= 0 ? 2 : 0);
  const nextStop = after.search(/[.!?](?:\s|$)/);
  const sentenceEnd = nextStop >= 0 ? end + nextStop + 1 : lineText.length;
  return cleanClaim(lineText.slice(sentenceStart, sentenceEnd));
}

function demoVerdict(citationKey) {
  return DEMO_VERDICTS[citationKey] || {
    verdict: "SUPPORT",
    label: "Supported",
    confidence: 0.86,
    annotation: "Local preview only",
    rationale: "This is a deterministic interface preview. Open the cited paper to verify the claim against the original evidence.",
  };
}

function clearEditorAnnotations() {
  document.querySelectorAll(".claimtrace-citation-line").forEach((line) => {
    line.classList.remove("claimtrace-citation-line", "claimtrace-tone-support", "claimtrace-tone-partial", "claimtrace-tone-danger", "claimtrace-focus-line", "claimtrace-hover-line");
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
    CSS.highlights.delete("claimtrace-citation-active");
  }
}

function getHoverCard() {
  let card = document.getElementById("claimtrace-citation-hover");
  if (card) return card;
  card = document.createElement("aside");
  card.id = "claimtrace-citation-hover";
  card.setAttribute("role", "tooltip");
  card.innerHTML = `
    <div class="claimtrace-hover-top"><span class="claimtrace-hover-verdict"></span><small class="claimtrace-hover-confidence"></small></div>
    <section class="claimtrace-hover-section claimtrace-hover-claim-section"><span>Claim</span><strong class="claimtrace-hover-claim"></strong></section>
    <section class="claimtrace-hover-source"><span>Source</span><strong class="claimtrace-hover-title"></strong><small class="claimtrace-hover-meta"></small><code class="claimtrace-hover-key"></code></section>
    <section class="claimtrace-hover-section"><span>Assessment</span><p class="claimtrace-hover-detail"></p><small class="claimtrace-hover-annotation"></small></section>
    <footer>Local preview · no backend verification</footer>
  `;
  document.body.appendChild(card);
  return card;
}

function showCitationHover(target) {
  window.clearTimeout(hoverHideTimer);
  if (!target) return;
  const { finding, line, range } = target;
  const tone = finding.verdict === "SUPPORT" ? "support" : finding.verdict === "PARTIAL" ? "partial" : "danger";
  const source = paperLibrary.get(finding.citationKey);
  const card = getHoverCard();
  card.className = `claimtrace-hover-visible claimtrace-hover-${tone}`;
  card.querySelector(".claimtrace-hover-verdict").textContent = finding.label;
  card.querySelector(".claimtrace-hover-confidence").textContent = `Demo signal ${Math.round(finding.confidence * 100)}%`;
  card.querySelector(".claimtrace-hover-claim").textContent = finding.claim;
  card.querySelector(".claimtrace-hover-title").textContent = source?.title || "Source details unavailable";
  card.querySelector(".claimtrace-hover-meta").textContent = source
    ? [source.authors, source.venue, source.year].filter(Boolean).join(" · ")
    : "No matching bibliography entry";
  card.querySelector(".claimtrace-hover-key").textContent = `\\cite{${finding.citationKey}}`;
  card.querySelector(".claimtrace-hover-detail").textContent = finding.rationale;
  card.querySelector(".claimtrace-hover-annotation").textContent = finding.annotation;

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
}

function hideCitationHover(delay = 80) {
  window.clearTimeout(hoverHideTimer);
  hoverHideTimer = window.setTimeout(() => {
    document.getElementById("claimtrace-citation-hover")?.classList.remove("claimtrace-hover-visible");
    activeCitationTarget?.line.classList.remove("claimtrace-hover-line");
    activeCitationTarget = undefined;
    if (typeof CSS !== "undefined") CSS.highlights?.delete("claimtrace-citation-active");
  }, delay);
}

function installCitationHighlights() {
  if (typeof CSS === "undefined" || !CSS.highlights || typeof Highlight === "undefined") return;
  ["support", "partial", "danger"].forEach((tone) => {
    const ranges = citationTargets.filter((target) => target.tone === tone).map((target) => target.range);
    if (ranges.length) CSS.highlights.set(`claimtrace-citations-${tone}`, new Highlight(...ranges));
  });
}

function annotateCitationLines() {
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
      const range = rangeForOffsets(line, match.index, CITE_PATTERN.lastIndex);
      const keys = match[1].split(",").map((key) => key.trim()).filter(Boolean);
      keys.forEach((citationKey, keyIndex) => {
        const preview = demoVerdict(citationKey);
        const locationId = `${lineIndex + 1}-${match.index}-${keyIndex}-${citationKey}`;
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
          preview: true,
        };
        findings.push(finding);
        lineFindings.push(finding);
        const tone = finding.verdict === "SUPPORT" ? "support" : finding.verdict === "PARTIAL" ? "partial" : "danger";
        const target = { finding, line, range, tone };
        citationLocations.set(locationId, target);
        if (range) citationTargets.push(target);
      });
    }

    if (!lineFindings.length) return;
    const strongest = lineFindings.reduce((current, finding) =>
      VERDICT_PRIORITY[finding.verdict] > VERDICT_PRIORITY[current.verdict] ? finding : current,
    );
    const tone = strongest.verdict === "SUPPORT" ? "support" : strongest.verdict === "PARTIAL" ? "partial" : "danger";
    line.classList.add("claimtrace-citation-line", `claimtrace-tone-${tone}`);
    line.dataset.claimtraceLabel = `ClaimTrace · local preview · ${strongest.label}`;
    line.dataset.claimtraceLocation = strongest.id;
    citationLineFindings.set(line, lineFindings);
  });

  installCitationHighlights();
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
      chrome.runtime.sendMessage({ type: "bibliography_detected", papers });
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
      hideCitationHover(0);
    }, 1800);
  }, 350);
  sendResponse({ found: true });
});

let pointerFrame;
document.addEventListener("mousemove", (event) => {
  if (pointerFrame) return;
  pointerFrame = window.requestAnimationFrame(() => {
    pointerFrame = undefined;
    const target = citationTargets.find(({ range }) => Array.from(range.getClientRects()).some((rect) =>
      event.clientX >= rect.left && event.clientX <= rect.right && event.clientY >= rect.top && event.clientY <= rect.bottom,
    ));
    if (target) {
      if (target !== activeCitationTarget) showCitationHover(target);
      else window.clearTimeout(hoverHideTimer);
    } else if (activeCitationTarget) {
      hideCitationHover();
    }
  });
});
document.addEventListener("mouseleave", () => hideCitationHover(0));

chrome.storage.local.get(["claimtracePapers"], ({ claimtracePapers }) => mergePaperLibrary(claimtracePapers));
chrome.storage.onChanged.addListener((changes, areaName) => {
  if (areaName === "local" && changes.claimtracePapers?.newValue) mergePaperLibrary(changes.claimtracePapers.newValue);
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
