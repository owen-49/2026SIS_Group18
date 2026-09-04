import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { listPapers, runAudit, usingMockApi } from "../api/client";
import { Icon } from "../components/Icon";
import { VerdictBadge } from "../components/VerdictBadge";
import { demoAudit } from "../data/mockData";
import { getWorkspacePapers } from "../data/workspacePapers";
import type { AuditResponse, ParseStatus, Verdict } from "../types/api";

type Filter = "ALL" | "FLAGGED" | Verdict;

interface AuditLocationState {
  fileName?: string;
  paperId?: string;
  justUploaded?: boolean;
}

interface AuditPaperOption {
  paperId: string;
  fileName: string;
  fileType?: "pdf" | "bib";
  status?: ParseStatus;
  pages?: number;
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
  const [audit, setAudit] = useState<AuditResponse | null>(usingMockApi ? demoAudit : null);
  const [loading, setLoading] = useState(false);
  const [papersLoading, setPapersLoading] = useState(!usingMockApi);
  const [papersError, setPapersError] = useState<string | null>(null);
  const [auditError, setAuditError] = useState<string | null>(null);
  const [filter, setFilter] = useState<Filter>("ALL");
  const [query, setQuery] = useState("");
  const [selectedKey, setSelectedKey] = useState(demoAudit.results[0]?.citation_key || "");
  const [hoveredKey, setHoveredKey] = useState<string | null>(null);
  const [showComplete, setShowComplete] = useState(false);
  const citationDocumentRef = useRef<HTMLDivElement>(null);
  const [papers, setPapers] = useState<AuditPaperOption[]>(() => usingMockApi ? getWorkspacePapers() : []);
  const [currentPaperId, setCurrentPaperId] = useState(() => (
    locationState?.paperId
      || (usingMockApi ? getWorkspacePapers()[0]?.paperId || "" : "")
  ));
  const currentPaper = papers.find((paper) => paper.paperId === currentPaperId) || papers[0];
  const manuscriptName = currentPaper?.fileName || locationState?.fileName || audit?.manuscript_id || "transformer-survey.pdf";

  useEffect(() => {
    if (usingMockApi) return;
    const controller = new AbortController();
    setPapersLoading(true);
    setPapersError(null);
    void listPapers(controller.signal).then((response) => {
      if (controller.signal.aborted) return;
      const pdfs = response.papers
        .filter((paper) => paper.file_type === "pdf")
        .map((paper) => ({
          paperId: paper.paper_id,
          fileName: paper.original_filename,
          fileType: paper.file_type,
          status: paper.status,
          pages: paper.pages,
        }));
      setPapers(pdfs);
      setCurrentPaperId((current) => {
        if (current && pdfs.some((paper) => paper.paperId === current)) return current;
        if (locationState?.paperId && pdfs.some((paper) => paper.paperId === locationState.paperId)) return locationState.paperId;
        return pdfs[0]?.paperId || "";
      });
    }).catch((error: unknown) => {
      if (!controller.signal.aborted) {
        setPapersError(error instanceof Error ? error.message : "Unable to load uploaded manuscripts.");
      }
    }).finally(() => {
      if (!controller.signal.aborted) setPapersLoading(false);
    });
    return () => controller.abort();
  }, [locationState?.paperId]);

  const sourcePaperIds = useMemo(
    () => papers.filter((paper) => paper.paperId !== currentPaperId
      && paper.fileType !== "bib"
      && (usingMockApi || paper.status === "completed"))
      .map((paper) => paper.paperId),
    [currentPaperId, papers],
  );

  useEffect(() => {
    if (usingMockApi) return;
    setAudit(null);
    setSelectedKey("");
    setAuditError(null);
  }, [currentPaperId]);

  useEffect(() => {
    if (!locationState?.justUploaded) return;
    const timer = window.setTimeout(() => setShowComplete(true), 850);
    return () => window.clearTimeout(timer);
  }, [locationState?.justUploaded]);

  async function refreshAudit() {
    setLoading(true);
    setAuditError(null);
    try {
      const response = await runAudit(currentPaperId, sourcePaperIds);
      setAudit(response);
      setSelectedKey(response.results[0]?.citation_key || "");
    } catch (error) {
      setAuditError(error instanceof Error ? error.message : "Unable to run the citation audit.");
    } finally {
      setLoading(false);
    }
  }

  function scrollToManuscriptClaim(citationKey: string) {
    window.setTimeout(() => {
      document.getElementById(`source-${citationKey}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
    });
  }

  function focusCitation(citationKey: string) {
    setSelectedKey(citationKey);
    scrollToManuscriptClaim(citationKey);
  }

  const results = useMemo(() => (audit?.results || []).filter((item) => {
    const matchesFilter = filter === "ALL"
      || (filter === "FLAGGED" ? item.risk_level === "high" : item.verdict === filter);
    const value = query.toLowerCase();
    return matchesFilter && (!value || item.claim.toLowerCase().includes(value) || item.citation_key.toLowerCase().includes(value));
  }), [audit, filter, query]);

  const selectedCitation = audit?.results.find((item) => item.citation_key === selectedKey) || audit?.results[0] || null;

  const scrollToSourceMatch = useCallback(() => {
    const container = citationDocumentRef.current;
    const match = container?.querySelector<HTMLElement>("[data-source-match='true']");
    if (!container || !match) return;
    const top = match.getBoundingClientRect().top - container.getBoundingClientRect().top + container.scrollTop - 48;
    container.scrollTo({ top, behavior: "smooth" });
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(scrollToSourceMatch, 80);
    return () => window.clearTimeout(timer);
  }, [scrollToSourceMatch, selectedCitation?.citation_key]);

  function chooseFilter(nextFilter: Filter) {
    setFilter(nextFilter);
    const firstMatch = audit?.results.find((item) => nextFilter === "ALL"
      || (nextFilter === "FLAGGED" ? item.risk_level === "high" : item.verdict === nextFilter));
    if (firstMatch) focusCitation(firstMatch.citation_key);
  }

  function revealSelectedCitation() {
    document.getElementById("selected-citation-document")?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  const markClass = (citationKey: string, tone: "support" | "partial" | "danger") =>
    `source-mark source-mark-${tone}${selectedKey === citationKey ? " selected" : ""}`;

  const sentenceClass = (citationKey: string, tone: "support" | "partial" | "danger") =>
    `citation-sentence citation-sentence-${tone}${hoveredKey === citationKey || selectedKey === citationKey ? " active" : ""}`;

  const supportPercentage = audit?.total_citations ? audit.supported / audit.total_citations * 100 : 0;
  const partialPercentage = audit?.total_citations ? audit.partial / audit.total_citations * 100 : 0;
  const highRiskPercentage = audit?.total_citations
    ? (audit.contradicted + audit.not_found) / audit.total_citations * 100
    : 0;

  return (
    <div className="page-stack audit-review-page">
      <section className="page-heading heading-row">
        <div><span className="eyebrow">Risk-ranked review</span><h1>Batch audit</h1><p>Inspect every result in the original manuscript context and jump directly to the cited sentence.</p></div>
        <div className="audit-heading-actions">
          <label className="manuscript-picker"><span>Current manuscript</span><select value={currentPaperId} disabled={!usingMockApi && (papersLoading || Boolean(papersError) || papers.length === 0)} onChange={(event) => setCurrentPaperId(event.target.value)}>{papers.map((paper) => <option value={paper.paperId} key={paper.paperId}>{paper.fileName}</option>)}</select></label>
          <button className="button button-primary" type="button" disabled={loading || (!usingMockApi && (!currentPaperId || sourcePaperIds.length === 0))} onClick={() => void refreshAudit()}>{loading ? <><span className="spinner" /> Auditing…</> : <><Icon name="audit" size={17} /> Run audit</>}</button>
        </div>
      </section>

      {!usingMockApi && papersLoading && <section className="library-state panel" role="status"><span className="library-state-icon"><span className="spinner" /></span><h2>Loading uploaded manuscripts</h2><p>Reading persisted PDF records from your Paper Library.</p></section>}
      {!usingMockApi && !papersLoading && papersError && <section className="library-state library-error panel" role="alert"><span className="library-state-icon"><Icon name="x" /></span><h2>Couldn’t load uploaded manuscripts</h2><p>{papersError}</p><button className="button button-secondary" type="button" onClick={() => window.location.reload()}>Try again</button></section>}
      {!usingMockApi && !papersLoading && !papersError && papers.length === 0 && <section className="library-state panel"><span className="library-state-icon"><Icon name="document" /></span><h2>No uploaded PDF manuscript</h2><p>Upload a manuscript and at least one source PDF in Paper Library before running an audit.</p></section>}
      {!usingMockApi && !papersLoading && !papersError && papers.length > 0 && sourcePaperIds.length === 0 && <section className="library-state panel"><span className="library-state-icon"><Icon name="search" /></span><h2>No source PDF selected</h2><p>Upload at least one additional completed PDF so the manuscript claims can be compared with source evidence.</p></section>}
      {auditError && <section className="library-state library-error panel" role="alert"><span className="library-state-icon"><Icon name="x" /></span><h2>Audit could not be completed</h2><p>{auditError}</p></section>}

      {audit && <>
        <section className="audit-summary panel">
          <div className="audit-score"><div className="score-ring"><strong>{Math.round(supportPercentage)}</strong><small>% supported</small></div><div><span className="eyebrow">{manuscriptName}</span><h2>{audit.total_citations} citations checked</h2><p>{audit.contradicted + audit.not_found} high-risk claims should be reviewed before submission.</p></div></div>
          <div className="summary-bars"><div><span>Supported <b>{audit.supported}</b></span><i><em style={{ width: `${supportPercentage}%` }} /></i></div><div><span>Partial <b>{audit.partial}</b></span><i><em className="partial-bar" style={{ width: `${partialPercentage}%` }} /></i></div><div><span>Contradicted / missing <b>{audit.contradicted + audit.not_found}</b></span><i><em className="danger-bar" style={{ width: `${highRiskPercentage}%` }} /></i></div></div>
        </section>

        <section className="audit-review-grid">
          <article className="panel manuscript-panel">
            <header className="manuscript-toolbar">
              <div><h2>Original manuscript</h2><p>{manuscriptName}</p></div>
              <span>{usingMockApi ? "Full demo manuscript · 12 pages" : audit.manuscript_document ? `Parsed manuscript · ${audit.manuscript_document.total_pages} pages` : "Parsed manuscript"}</span>
            </header>
            <div className="manuscript-scroll">
              {usingMockApi && <>{Array.from({ length: 12 }, (_, index) => index + 1).map((page) => {
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
              })}</>}
              {!usingMockApi && audit.manuscript_document ? audit.manuscript_document.pages.map((page) => (
                <section className="manuscript-sheet" aria-label={`Manuscript page ${page.page}`} key={page.page}>
                  <small>{page.page} / {audit.manuscript_document?.total_pages}</small>
                  {page.heading && <h2>{page.heading}</h2>}
                  {page.paragraphs.map((paragraph, paragraphIndex) => {
                    const matched = audit.results.find((item) => item.manuscript_location?.page === page.page
                      && item.manuscript_location.paragraph_index === paragraphIndex);
                    if (!matched) return <p key={`${page.page}-${paragraphIndex}`}>{paragraph}</p>;
                    const tone = matched.verdict === "SUPPORT" ? "support" : matched.verdict === "PARTIAL" ? "partial" : "danger";
                    return <p className={sentenceClass(matched.citation_key, tone)} data-manuscript-match={selectedKey === matched.citation_key ? "true" : undefined} key={`${page.page}-${paragraphIndex}`}>
                      {paragraph} <button id={`source-${matched.citation_key}`} className={markClass(matched.citation_key, tone)} type="button" onFocus={() => setHoveredKey(matched.citation_key)} onBlur={() => setHoveredKey(null)} onClick={() => focusCitation(matched.citation_key)}>{matched.citation_key}</button>
                    </p>;
                  })}
                </section>
              )) : !usingMockApi ? <div className="manuscript-loading"><Icon name="audit" /><strong>Run the audit to load the parsed manuscript.</strong></div> : null}
            </div>
          </article>

          <aside className="panel findings-panel">
            <div className="findings-heading"><div><h2>Citation findings</h2><p>Select a finding to locate it in the original text.</p></div><span>{results.length} shown</span></div>
            <label className="search-field compact findings-search"><Icon name="search" size={17} /><span className="sr-only">Search findings</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search citations…" /></label>
            <div className="filter-tabs findings-filters">{filterOptions.map((option) => <button className={filter === option.value ? "active" : ""} key={option.value} onClick={() => chooseFilter(option.value)}>{option.label}</button>)}</div>
            <div className="finding-list">
              {results.map((item) => (
                <button className={selectedKey === item.citation_key ? "finding-card active" : "finding-card"} type="button" key={`${item.citation_key}-${item.claim}`} onClick={() => focusCitation(item.citation_key)}>
                  <span className={`risk-dot risk-${item.risk_level}`} />
                  <span className="finding-copy"><strong>{item.claim}</strong><small>Page {item.manuscript_location?.page || "—"} · <code>{item.citation_key}</code></small>{item.source_location?.annotation && <em>{item.source_location.annotation}</em>}</span>
                  <span className="finding-result"><VerdictBadge verdict={item.verdict} /><small>{usingMockApi ? "Demo signal" : "Confidence"} {Math.round(item.confidence * 100)}%</small></span>
                </button>
              ))}
              {results.length === 0 && <div className="table-empty">No citations match this view.</div>}
            </div>
          </aside>
        </section>

        {selectedCitation && (
          <section className="panel citation-evidence-panel" id="selected-citation-document">
            <header className="citation-evidence-heading">
              <div><span className="eyebrow">Selected citation</span><h2>{selectedCitation.cited_source?.title || selectedCitation.citation_key}</h2><p>{selectedCitation.cited_source ? `${selectedCitation.cited_source.authors.join(", ")} · ${selectedCitation.cited_source.venue || "Unknown venue"} · ${selectedCitation.cited_source.year || "Unknown year"}` : "The original cited article could not be confirmed in an academic database."}</p></div>
              <VerdictBadge verdict={selectedCitation.verdict} />
            </header>
            <div className="citation-evidence-grid">
              <article className="citation-source-reader">
                <header className="manuscript-toolbar citation-source-toolbar"><div><h2>Citation article — full original text</h2><p>{selectedCitation.cited_source?.title || selectedCitation.citation_key}</p></div><div><span>{selectedCitation.source_document ? usingMockApi ? "Complete demo document" : selectedCitation.source_document.pages.length === selectedCitation.source_document.total_pages ? `Complete · ${selectedCitation.source_document.total_pages} pages` : `${selectedCitation.source_document.pages.length} of ${selectedCitation.source_document.total_pages} pages` : selectedCitation.cited_source?.database || "Academic database"}</span>{selectedCitation.source_document?.matched_location && <button className="button button-secondary" type="button" onClick={scrollToSourceMatch}><Icon name="search" size={14} /> Jump to AI match</button>}</div></header>
                {selectedCitation.source_document ? (
                  <div className="manuscript-scroll citation-source-scroll" ref={citationDocumentRef}>
                    {selectedCitation.source_document.pages.map((page) => (
                      <section className="manuscript-sheet citation-source-sheet" key={page.page}>
                        <small>{page.page} / {selectedCitation.source_document?.total_pages}</small>
                        {page.heading && <h2>{page.heading}</h2>}
                        {page.paragraphs.map((paragraph, paragraphIndex) => {
                          const matched = selectedCitation.source_document?.matched_location?.page === page.page
                            && selectedCitation.source_document.matched_location.paragraph_index === paragraphIndex;
                          return <p className={matched ? "matched-source-paragraph" : ""} data-source-match={matched ? "true" : undefined} key={`${page.page}-${paragraphIndex}`}>{paragraph}{matched && <mark>AI matched passage · Page {page.page}, paragraph {paragraphIndex + 1}</mark>}</p>;
                        })}
                      </section>
                    ))}
                  </div>
                ) : <div className="citation-source-empty">{selectedCitation.source_passage ? <blockquote>“{selectedCitation.source_passage}”</blockquote> : <div className="missing-source-passage"><Icon name="search" size={20} /><span><strong>Original text unavailable</strong><p>The cited article was not found, so ClaimTrace cannot present or verify its source passage.</p></span></div>}</div>}
                {selectedCitation.cited_source?.url && <footer className="citation-source-footer"><a className="inline-link" href={selectedCitation.cited_source.url} target="_blank" rel="noreferrer">Open database record <Icon name="external" size={14} /></a></footer>}
              </article>
            </div>
            {!selectedCitation.cited_source && selectedCitation.similar_sources?.length ? <div className="audit-similar-sources"><strong>Similar database result</strong>{selectedCitation.similar_sources.map((source) => <span key={source.source_paper_id || source.citation_key}>{source.title}<small>{Math.round(source.similarity * 100)}% title/metadata similarity · not the confirmed citation</small></span>)}</div> : null}
          </section>
        )}

        {selectedCitation && (
          <section className="audit-ai-dock" aria-live="polite">
            <div className="audit-ai-dock-inner">
              <div className="audit-ai-dock-title"><span><Icon name="spark" size={16} /></span><div><small>AI comparison</small><strong>{selectedCitation.citation_key}</strong></div></div>
              <div className="audit-ai-comparison-flow">
                <article className="audit-ai-claim" role="button" tabIndex={0} title="Locate this claim in the original manuscript" onMouseEnter={() => scrollToManuscriptClaim(selectedCitation.citation_key)} onFocus={() => scrollToManuscriptClaim(selectedCitation.citation_key)} onClick={() => scrollToManuscriptClaim(selectedCitation.citation_key)} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); scrollToManuscriptClaim(selectedCitation.citation_key); } }}><span>Manuscript claim · hover to locate</span><p>“{selectedCitation.claim}”</p></article>
                <span className="audit-ai-flow-arrow"><Icon name="arrow" size={17} /></span>
                <article className="audit-ai-assessment"><span>Assessment</span><p>{selectedCitation.comparison_rationale || "No AI comparison explanation was returned for this citation."}</p></article>
              </div>
              <div className="audit-ai-dock-result"><div><VerdictBadge verdict={selectedCitation.verdict} /><strong>{Math.round(selectedCitation.confidence * 100)}%</strong></div><button className="button button-secondary" type="button" disabled={!selectedCitation.cited_source} onClick={revealSelectedCitation}>{selectedCitation.cited_source ? "Full article" : "Source missing"} <Icon name="arrow" size={14} /></button>{usingMockApi && <small>Demo signal</small>}</div>
            </div>
          </section>
        )}
      </>}

      {showComplete && usingMockApi && (
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
