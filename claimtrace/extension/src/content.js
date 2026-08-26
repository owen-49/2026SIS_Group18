/**
 * ClaimTrace Overleaf Content Script.
 *
 * Injects into Overleaf project pages. Listens for hover events
 * on \cite{...} elements and queries the ClaimTrace API.
 *
 * v0.1: Detects citation elements and logs hover events.
 *       Popup with real data coming in Sprint 3 (W7-W8).
 */

const API_BASE = "http://localhost:8000";

// ── DOM Detection ──────────────────────────────────────────────

/**
 * Find citation elements in Overleaf's editor DOM.
 *
 * Overleaf renders \cite{key} as a clickable span.
 * v0.1 selector: broad match, may need tuning per Overleaf updates.
 */
function findCitationElements() {
  // Overleaf's Ace editor renders citations with specific classes
  // This selector is a starting point — validate during W1 Spike 3
  const selectors = [
    '[data-cy="citation"]',
    ".citation-element",
    ".ace_cite", // fallback
  ];

  for (const sel of selectors) {
    const elements = document.querySelectorAll(sel);
    if (elements.length > 0) {
      return Array.from(elements);
    }
  }

  return [];
}

// ── Hover Handler ──────────────────────────────────────────────

let currentPopup = null;
function showPopup(citationKey, x, y) {
  hidePopup();

  const popup = document.createElement("div");
  popup.className = "claimtrace-popup";
  popup.innerHTML = `
    <div class="claimtrace-popup-header">
      <span class="claimtrace-key">\\cite{${citationKey}}</span>
      <span class="claimtrace-loading">Checking...</span>
    </div>
    <div class="claimtrace-popup-body">
      <p>Loading verification from ClaimTrace...</p>
    </div>
  `;

  popup.style.position = "fixed";
  popup.style.left = `${x + 10}px`;
  popup.style.top = `${y + 10}px`;
  popup.style.zIndex = "99999";

  document.body.appendChild(popup);
  currentPopup = popup;

  // TODO W7-W8: Fetch real verification from API
  // fetch(`${API_BASE}/api/verify/cite/${citationKey}`)
  //   .then(r => r.json())
  //   .then(data => updatePopup(data));
}

function hidePopup() {
  if (currentPopup) {
    currentPopup.remove();
    currentPopup = null;
  }
}

// ── Initialize ─────────────────────────────────────────────────



function getPageContent() {
  const editor = document.querySelector(".cm-content");

  return {
    title: document.title,
    url: window.location.href,
    editorFound: !!editor,

    content: editor
      ? editor.innerText
      : document.body.innerText
  };
}

chrome.runtime.onMessage.addListener(
  (message, sender, sendResponse) => {

    if (message.action === "getPageContent") {

      const pageData = getPageContent();

      console.log(
        "[ClaimTrace] Page content requested."
      );

      console.log(pageData);

      sendResponse(pageData);
    }
  }
);

function init() {
  console.log("[ClaimTrace] Extension loaded on Overleaf page.");

  // Phase 1 (W1-W3): Passive detection only — log citation element count
  const citations = findCitationElements();
  console.log(`[ClaimTrace] Found ${citations.length} potential citation elements.`);

  // TODO W7-W8: Attach hover listeners to citation elements
  // citations.forEach(el => {
  //   el.addEventListener("mouseenter", (e) => {
  //     const key = extractCitationKey(el);
  //     if (key) showPopup(key, e.clientX, e.clientY);
  //   });
  //   el.addEventListener("mouseleave", hidePopup);
  // });
}

// Run when DOM is ready
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}

// Export for debugging
// export { findCitationElements, showPopup, hidePopup };
