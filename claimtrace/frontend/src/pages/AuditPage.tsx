import { useEffect, useMemo, useState } from "react";
import { useLocation } from "react-router-dom";
import { runAudit, usingMockApi } from "../api/client";
import { Icon } from "../components/Icon";
import { VerdictBadge } from "../components/VerdictBadge";
import { demoAudit } from "../data/mockData";
import { getWorkspacePapers } from "../data/workspacePapers";
import type { AuditResponse, Verdict } from "../types/api";

type Filter = "ALL" | "FLAGGED" | Verdict;

interface AuditLocationState {
  fileName?: string;
  paperId?: string;
  justUploaded?: boolean;
}

const filterOptions: { value: Filter; label: string }[] = [
  { value: "ALL", label: "All citations" },
  { value: "FLAGGED", label: "Flagged" },
  { value: "CONTRADICT", label: "Contradicted" },
  { value: "PARTIAL", label: "Partial" },
  { value: "SUPPORT", label: "Supported" },
  { value: "NOT_FOUND", label: "Not found" },
];

const demoPageCopy: Record<number, { title: string; paragraphs: string[] }> = {
  1: { title: "AI in Scientific Discovery", paragraphs: ["A citation-aware review of language models, retrieval systems, and evidence validation.", "Abstract — Artificial intelligence increasingly supports literature discovery, hypothesis generation, and scientific writing. This paper reviews recent systems and examines how accurately their claims remain connected to published evidence.", "Keywords: scientific discovery, language models, citation verification, retrieval-augmented generation."] },
  2: { title: "1. Introduction", paragraphs: ["Scientific knowledge is growing faster than any individual researcher can read. Machine-assisted discovery tools help organise this literature and surface connections between distant fields.", "Reliable citation practice remains essential. A fluent sentence may overstate, misread, or cite a source that does not contain the claimed evidence.", "We study a workflow that connects every cited claim to its source passage and presents questionable citations for human review."] },
  5: { title: "4. Methodology", paragraphs: ["The review pipeline separates manuscript parsing, citation extraction, source retrieval, and evidence comparison into independent stages.", "Each manuscript sentence is associated with its citation marker and page location. Candidate evidence passages are retrieved from the linked source document.", "The final review interface preserves the manuscript context so researchers can inspect a result without losing their place in the paper."] },
  6: { title: "5. Experimental Setup", paragraphs: ["We evaluate the workflow on a small collection of academic manuscripts containing supported, partially supported, contradictory, and missing-source examples.", "Reviewers label each claim using the cited paper and record whether the system identifies the correct manuscript location.", "Interface measurements include time to locate a citation, correction accuracy, and agreement between reviewers."] },
  7: { title: "6. Results", paragraphs: ["Context-preserving review reduced the time required to locate flagged claims. Reviewers moved directly from a finding to the corresponding sentence.", "Supported claims were typically resolved quickly, while partially supported claims required closer inspection of scope and qualifications.", "Missing documents remained the most common reason that a citation could not be fully assessed."] },
  8: { title: "7. Discussion", paragraphs: ["Citation verification should support scholarly judgement rather than replace it. Automated signals are most useful when they reveal evidence and preserve uncertainty.", "Showing the original manuscript is especially important because a claim can only be interpreted correctly within its surrounding argument.", "A practical system should also distinguish model-generated signals from verified bibliographic facts."] },
  9: { title: "8. Limitations", paragraphs: ["The current study uses a limited document collection and does not represent every academic discipline or citation style.", "Scanned documents, mathematical notation, tables, and multi-column layouts may reduce extraction quality.", "Confidence values require calibration before they can be interpreted as probabilities in production use."] },
  10: { title: "9. Conclusion", paragraphs: ["Evidence-aware citation review can make scholarly writing more transparent and easier to audit.", "The most useful interface links each finding to the exact sentence, citation marker, source document, and supporting passage.", "Future work will evaluate the complete pipeline on larger, expert-reviewed datasets."] },
  11: { title: "References", paragraphs: ["[1] Vaswani, A. et al. Attention Is All You Need. NeurIPS, 2017.", "[2] Devlin, J. et al. BERT: Pre-training of Deep Bidirectional Transformers. NAACL, 2019.", "[3] Brown, T. et al. Language Models are Few-Shot Learners. NeurIPS, 2020.", "[4] Lewis, P. et al. Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks. NeurIPS, 2020."] },
  12: { title: "Appendix A. Review Protocol", paragraphs: ["Reviewers first read the complete sentence containing a citation and then inspect the retrieved source passage.", "A claim is marked as supported only when the cited evidence directly establishes the stated conclusion.", "Disagreements are recorded for adjudication rather than hidden behind a single automated score."] },
};

export function AuditPage() {
  const location = useLocation();
  const locationState = location.state as AuditLocationState | null;
  const [audit, setAudit] = useState<AuditResponse | null>(demoAudit);
  const [loading, setLoading] = useState(false);
  const [filter, setFilter] = useState<Filter>("ALL");
  const [query, setQuery] = useState("");
  const [selectedKey, setSelectedKey] = useState("");
  const [hoveredKey, setHoveredKey] = useState<string | null>(null);
  const [showComplete, setShowComplete] = useState(false);
  const [papers] = useState(getWorkspacePapers);
  const [currentPaperId, setCurrentPaperId] = useState(() => locationState?.paperId || getWorkspacePapers()[0].paperId);
  const currentPaper = papers.find((paper) => paper.paperId === currentPaperId) || papers[0];
  const manuscriptName = currentPaper?.fileName || locationState?.fileName || audit?.manuscript_id || "transformer-survey.pdf";

  useEffect(() => {
    if (!locationState?.justUploaded) return;
    const timer = window.setTimeout(() => setShowComplete(true), 850);
    return () => window.clearTimeout(timer);
  }, [locationState?.justUploaded]);

  async function refreshAudit() {
    setLoading(true);
    try {
      setAudit(await runAudit(currentPaperId, ["paper-attention", "paper-bert", "paper-gpt3", "paper-rag"]));
    } finally {
      setLoading(false);
    }
  }

  function focusCitation(citationKey: string) {
    setSelectedKey(citationKey);
    window.setTimeout(() => {
      document.getElementById(`source-${citationKey}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
    });
  }

  const results = useMemo(() => (audit?.results || []).filter((item) => {
    const matchesFilter = filter === "ALL"
      || (filter === "FLAGGED" ? item.risk_level === "high" : item.verdict === filter);
    const value = query.toLowerCase();
    return matchesFilter && (!value || item.claim.toLowerCase().includes(value) || item.citation_key.toLowerCase().includes(value));
  }), [audit, filter, query]);

  const markClass = (citationKey: string, tone: "support" | "partial" | "danger") =>
    `source-mark source-mark-${tone}${selectedKey === citationKey ? " selected" : ""}`;

  const sentenceClass = (citationKey: string, tone: "support" | "partial" | "danger") =>
    `citation-sentence citation-sentence-${tone}${hoveredKey === citationKey || selectedKey === citationKey ? " active" : ""}`;

  return (
    <div className="page-stack audit-review-page">
      <section className="page-heading heading-row">
        <div><span className="eyebrow">Risk-ranked review</span><h1>Batch audit</h1><p>Inspect every result in the original manuscript context and jump directly to the cited sentence.</p></div>
        <div className="audit-heading-actions">
          <label className="manuscript-picker"><span>Current manuscript</span><select value={currentPaperId} onChange={(event) => setCurrentPaperId(event.target.value)}>{papers.map((paper) => <option value={paper.paperId} key={paper.paperId}>{paper.fileName}</option>)}</select></label>
          <button className="button button-primary" type="button" disabled={loading} onClick={() => void refreshAudit()}>{loading ? <><span className="spinner" /> Auditing…</> : <><Icon name="audit" size={17} /> Run audit</>}</button>
        </div>
      </section>

      {audit && <>
        <section className="audit-summary panel">
          <div className="audit-score"><div className="score-ring"><strong>{Math.round((audit.supported / audit.total_citations) * 100)}</strong><small>% supported</small></div><div><span className="eyebrow">{manuscriptName}</span><h2>{audit.total_citations} citations checked</h2><p>{audit.contradicted + audit.not_found} high-risk claims should be reviewed before submission.</p></div></div>
          <div className="summary-bars"><div><span>Supported <b>{audit.supported}</b></span><i><em style={{ width: `${audit.supported / audit.total_citations * 100}%` }} /></i></div><div><span>Partial <b>{audit.partial}</b></span><i><em className="partial-bar" style={{ width: `${audit.partial / audit.total_citations * 100}%` }} /></i></div><div><span>Contradicted / missing <b>{audit.contradicted + audit.not_found}</b></span><i><em className="danger-bar" style={{ width: `${(audit.contradicted + audit.not_found) / audit.total_citations * 100}%` }} /></i></div></div>
        </section>

        <section className="audit-review-grid">
          <article className="panel manuscript-panel">
            <header className="manuscript-toolbar">
              <div><h2>Original manuscript</h2><p>{manuscriptName}</p></div>
              <span>{usingMockApi ? "Full demo manuscript · 12 pages" : "Full manuscript · 12 pages"}</span>
            </header>
            <div className="manuscript-scroll">
              {Array.from({ length: 12 }, (_, index) => index + 1).map((page) => {
                if (page === 3) return (
                  <section className="manuscript-sheet" aria-label="Manuscript page 3" key={page}>
                    <small>3 / 12</small>
                    <h2>2. Related Work</h2>
                    <p>
                      Large language models have transformed modern scientific workflows, enabling researchers to discover patterns across large collections of text. <span className={sentenceClass("vaswani2017attention", "support")} onMouseEnter={() => setHoveredKey("vaswani2017attention")} onMouseLeave={() => setHoveredKey(null)}>The Transformer removes recurrence in favour of attention mechanisms <button id="source-vaswani2017attention" className={markClass("vaswani2017attention", "support")} type="button" onFocus={() => setHoveredKey("vaswani2017attention")} onBlur={() => setHoveredKey(null)} onClick={() => focusCitation("vaswani2017attention")}>[1]</button>.</span>{" "}
                      <span className={sentenceClass("devlin2019bert", "danger")} onMouseEnter={() => setHoveredKey("devlin2019bert")} onMouseLeave={() => setHoveredKey(null)}>BERT was trained exclusively with a next-sentence prediction objective <button id="source-devlin2019bert" className={markClass("devlin2019bert", "danger")} type="button" onFocus={() => setHoveredKey("devlin2019bert")} onBlur={() => setHoveredKey(null)} onClick={() => focusCitation("devlin2019bert")}>[2]</button>.</span>
                    </p>
                    <p>
                      <span className={sentenceClass("brown2020language", "partial")} onMouseEnter={() => setHoveredKey("brown2020language")} onMouseLeave={() => setHoveredKey(null)}>Recent studies suggest that larger language models always improve few-shot performance <button id="source-brown2020language" className={markClass("brown2020language", "partial")} type="button" onFocus={() => setHoveredKey("brown2020language")} onBlur={() => setHoveredKey(null)} onClick={() => focusCitation("brown2020language")}>[3]</button>.</span> These examples show why citation review must preserve the surrounding argument rather than inspect isolated markers.
                    </p>
                    <aside className="manuscript-callouts"><span className="callout-danger">Claim contradicts source [2]</span><span className="callout-partial">Evidence only partially supports [3]</span></aside>
                  </section>
                );

                if (page === 4) return (
                  <section className="manuscript-sheet" aria-label="Manuscript page 4" key={page}>
                    <small>4 / 12</small>
                    <h2>3. Retrieval-Augmented Models</h2>
                    <p><span className={sentenceClass("lewis2020retrieval", "support")} onMouseEnter={() => setHoveredKey("lewis2020retrieval")} onMouseLeave={() => setHoveredKey(null)}>Retrieval-augmented generation combines parametric and non-parametric memory <button id="source-lewis2020retrieval" className={markClass("lewis2020retrieval", "support")} type="button" onFocus={() => setHoveredKey("lewis2020retrieval")} onBlur={() => setHoveredKey(null)} onClick={() => focusCitation("lewis2020retrieval")}>[4]</button>.</span> This design enables a model to retrieve external evidence while retaining the fluency and generalisation of a pretrained generator.</p>
                    <p>Retrieved passages are combined with the model state before each generated response, allowing external documents to contribute facts without permanently changing model parameters. <span className={sentenceClass("smith2024survey", "danger")} onMouseEnter={() => setHoveredKey("smith2024survey")} onMouseLeave={() => setHoveredKey(null)}>Citation errors affect a majority of reviewed manuscripts <button id="source-smith2024survey" className={markClass("smith2024survey", "danger")} type="button" onFocus={() => setHoveredKey("smith2024survey")} onBlur={() => setHoveredKey(null)} onClick={() => focusCitation("smith2024survey")}>[5]</button>.</span></p>
                    <aside className="manuscript-callouts"><span className="callout-danger">Source not found [5]</span></aside>
                  </section>
                );

                const content = demoPageCopy[page];
                return (
                  <section className="manuscript-sheet" aria-label={`Manuscript page ${page}`} key={page}>
                    <small>{page} / 12</small>
                    <h2>{content.title}</h2>
                    {content.paragraphs.map((paragraph) => <p key={paragraph}>{paragraph}</p>)}
                  </section>
                );
              })}
            </div>
          </article>

          <aside className="panel findings-panel">
            <div className="findings-heading"><div><h2>Citation findings</h2><p>Select a finding to locate it in the original text.</p></div><span>{results.length} shown</span></div>
            <label className="search-field compact findings-search"><Icon name="search" size={17} /><span className="sr-only">Search findings</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search citations…" /></label>
            <div className="filter-tabs findings-filters">{filterOptions.map((option) => <button className={filter === option.value ? "active" : ""} key={option.value} onClick={() => setFilter(option.value)}>{option.label}</button>)}</div>
            <div className="finding-list">
              {results.map((item) => (
                <button className={selectedKey === item.citation_key ? "finding-card active" : "finding-card"} type="button" key={`${item.citation_key}-${item.claim}`} onClick={() => focusCitation(item.citation_key)}>
                  <span className={`risk-dot risk-${item.risk_level}`} />
                  <span className="finding-copy"><strong>{item.claim}</strong><small>Page {item.source_location?.page || "—"} · <code>{item.citation_key}</code></small>{item.source_location?.annotation && <em>{item.source_location.annotation}</em>}</span>
                  <span className="finding-result"><VerdictBadge verdict={item.verdict} /><small>{usingMockApi ? "Demo signal" : "Confidence"} {Math.round(item.confidence * 100)}%</small></span>
                </button>
              ))}
              {results.length === 0 && <div className="table-empty">No citations match this view.</div>}
            </div>
          </aside>
        </section>
      </>}

      {showComplete && (
        <div className="audit-complete-overlay" role="dialog" aria-modal="true" aria-labelledby="audit-complete-title">
          <section className="audit-complete-card">
            <span><Icon name="check" size={30} /></span>
            <h2 id="audit-complete-title">Citation review complete</h2>
            <p>12 references checked <i /> 2 demo issues found</p>
            <button className="button button-primary full-button" type="button" onClick={() => { setShowComplete(false); setFilter("FLAGGED"); focusCitation("devlin2019bert"); }}>Review flagged citations</button>
          </section>
        </div>
      )}
    </div>
  );
}
