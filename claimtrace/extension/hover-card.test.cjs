// US-02: hovering \cite{...} in Overleaf shows the original text.
//
// The card is exercised through the entry points the page uses -- the mousemove
// listener, the storage change the background writes after /api/verify, the
// focus_citation message -- rather than by reaching into the script. It cannot
// be reached into anyway: content.js is a classic script, so its top-level const
// and let bindings live in the script's own lexical scope and never appear on
// the context object. Only its function declarations do, and calling those
// directly would test the pieces instead of the path.
const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { createDom } = require("./fake-dom.cjs");

const CONTENT = fs.readFileSync(path.join(__dirname, "src/content.js"), "utf8");
const BIB = [
  "@article{lewis2020retrieval,",
  "  title = {Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks},",
  "  author = {Lewis, Patrick and Perez, Ethan},",
  "  journal = {NeurIPS},",
  "  year = {2020}",
  "}",
];
const CITATION = "Retrieval augmentation improves factual accuracy \\cite{lewis2020retrieval}.";
const CLAIM = "Retrieval augmentation improves factual accuracy [lewis2020retrieval].";
const PASSAGE = "We combine a parametric memory with a non-parametric dense retriever, which improves factual accuracy on knowledge-intensive tasks.";
// Where the citation line's rectangle sits, so a pointer move lands on it.
const ON_CITATION = [120, 110];
const AWAY = [700, 500];

function load(options = {}) {
  const dom = createDom({ lines: [...BIB, CITATION], ...options });
  vm.createContext(dom);
  vm.runInContext(CONTENT, dom);
  return dom;
}

// The finding the background stores after /api/verify answers, matching the
// shape background.js builds: real passage text from the parsed PDF, the match
// count in the annotation, and preview turned off.
function verify(dom, matches, overrides = {}) {
  const [detected] = dom.reports("citations_detected").at(-1).findings;
  dom.setFindings([{
    ...detected,
    verdict: "SUPPORT",
    label: "Supported",
    confidence: 0.82,
    annotation: `Backend verification · ${matches.length} matching passage(s)`,
    rationale: "The retrieved passage makes the same point.",
    matches,
    preview: false,
    ...overrides,
  }]);
  return detected;
}

const match = (passage_text, similarity) => ({ passage_text, similarity, entailment_label: "SUPPORT", confidence: 0.8 });

test("hovering a verified citation shows the retrieved passage, not only its count", () => {
  const dom = load();
  verify(dom, [match(PASSAGE, 0.87), match("A second paragraph.", 0.4), match("A third paragraph.", 0.2)]);
  dom.move(...ON_CITATION);

  assert.equal(dom.elementIn(".claimtrace-hover-passage").hidden, false);
  assert.equal(dom.textIn(".claimtrace-hover-quote"), PASSAGE);
  assert.equal(dom.textIn(".claimtrace-hover-provenance"), "Passage 1 of 3 · 87% lexical overlap");
  assert.equal(dom.textIn(".claimtrace-hover-title"), "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks");
  assert.equal(dom.textIn(".claimtrace-hover-annotation"), "Backend verification · 3 matching passage(s)");
});

test("the card shows the sentence the citation sits in", () => {
  const dom = load();
  dom.move(...ON_CITATION);
  assert.equal(dom.textIn(".claimtrace-hover-claim"), CLAIM);
  assert.equal(dom.elementIn(".claimtrace-hover-passage").hidden, true);
});

test("a citation that was never verified offers no passage", () => {
  const dom = load();
  dom.move(...ON_CITATION);

  assert.equal(dom.textIn(".claimtrace-hover-verdict"), "Pending verification");
  assert.equal(dom.elementIn(".claimtrace-hover-passage").hidden, true);
  assert.equal(dom.textIn(".claimtrace-hover-quote"), "");
});

test("a verified citation with no retrieved passages says so rather than quoting nothing", () => {
  const dom = load();
  verify(dom, []);
  dom.move(...ON_CITATION);

  assert.equal(dom.textIn(".claimtrace-hover-annotation"), "Backend verification · 0 matching passage(s)");
  assert.equal(dom.elementIn(".claimtrace-hover-passage").hidden, true);
});

test("a match without usable text is not rendered as an empty excerpt", () => {
  const dom = load();
  verify(dom, [{ similarity: 0.9 }, match("   ", 0.8)]);
  dom.move(...ON_CITATION);

  assert.equal(dom.elementIn(".claimtrace-hover-passage").hidden, true);
});

test("a passage carrying markup is shown as text, never parsed", () => {
  const dom = load();
  const hostile = '<img src=x onerror="boom()"> is a sentence in a PDF';
  verify(dom, [match(hostile, 1)]);
  dom.move(...ON_CITATION);

  const quote = dom.elementIn(".claimtrace-hover-quote");
  assert.equal(quote.textContent, hostile);
  assert.equal(quote.childNodes.length, 1);
  assert.equal(quote.childNodes[0].nodeType, 3);
  assert.equal(quote.querySelectorAll("img").length, 0);
  assert.equal(dom.textIn(".claimtrace-hover-provenance"), "Passage 1 of 1 · 100% lexical overlap");
});

test("the hover path reads memory only: no fetch, no message to the background", () => {
  const dom = load();
  verify(dom, [match(PASSAGE, 0.9)]);
  const reported = dom.messages.length;

  dom.move(...ON_CITATION);
  dom.move(140, 112);
  dom.move(...AWAY);
  dom.flushTimers();
  dom.move(...ON_CITATION);

  assert.equal(dom.fetches.length, 0);
  assert.equal(dom.messages.length, reported);
});

test("each hover takes one latency measurement and reports it to the console", () => {
  const dom = load();
  verify(dom, [match(PASSAGE, 0.9)]);

  dom.move(...ON_CITATION);
  assert.deepEqual(Array.from(dom.measures, (measure) => measure.name), ["claimtrace:hover"]);
  assert.deepEqual(dom.marks, ["claimtrace:hover:start"]);
  assert.ok(
    dom.logs.some((line) => /^\[ClaimTrace\] hover card in \d+(\.\d+)? ms$/.test(line)),
    `no hover measurement in the console: ${dom.logs.join(" | ")}`,
  );

  dom.move(...AWAY);
  dom.flushTimers();
  dom.move(...ON_CITATION);
  assert.equal(dom.measures.length, 2, "a second hover must be measured on its own, not reuse the first");
});

test("the card hides when the pointer leaves the citation", () => {
  const dom = load();
  verify(dom, [match(PASSAGE, 0.9)]);
  dom.move(...ON_CITATION);
  assert.equal(dom.hoverCard().classList.contains("claimtrace-hover-visible"), true);

  dom.move(...AWAY);
  dom.flushTimers();
  assert.equal(dom.hoverCard().classList.contains("claimtrace-hover-visible"), false);
});

test("focusing a citation from the side panel shows the card with its passage", () => {
  const dom = load();
  const detected = verify(dom, [match(PASSAGE, 0.9)]);
  const responses = dom.focusCitation(detected.id);

  assert.equal(responses.length, 1);
  assert.equal(responses[0].found, true);
  assert.equal(dom.hoverCard().classList.contains("claimtrace-hover-visible"), true);
  assert.equal(dom.textIn(".claimtrace-hover-quote"), PASSAGE);
});

test("the card still renders when the page offers no performance or CSS API", () => {
  const dom = load({ performance: false, css: false });
  verify(dom, [match(PASSAGE, 0.9)]);
  dom.move(...ON_CITATION);

  assert.equal(dom.hoverCard().classList.contains("claimtrace-hover-visible"), true);
  assert.equal(dom.textIn(".claimtrace-hover-quote"), PASSAGE);
});

test("citation detection, the bibliography prompt and highlights are unchanged", () => {
  const dom = load();
  const [finding] = dom.reports("citations_detected")[0].findings;
  const line = dom.document.querySelectorAll(".cm-line").at(-1);

  assert.equal(finding.citationKey, "lewis2020retrieval");
  assert.equal(finding.preview, true);
  assert.equal(line.classList.contains("claimtrace-citation-line"), true);
  assert.equal(line.dataset.claimtraceLabel, "ClaimTrace · local preview · Pending verification");
  assert.equal(dom.reports("bibliography_detected")[0].papers.length, 1);
  assert.equal(dom.highlights.has("claimtrace-citations-pending"), true);
  assert.equal(
    dom.document.getElementById("claimtrace-bib-prompt").querySelector(".claimtrace-prompt-open").textContent,
    "Open ClaimTrace",
  );
});
