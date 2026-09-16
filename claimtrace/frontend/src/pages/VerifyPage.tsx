import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { getPaperClaims, listPapers, usingMockApi as configuredMockApi, verifyCitation } from "../api/client";
import { Icon } from "../components/Icon";
import { UploadFilesButton } from "../components/UploadFilesButton";
import { CitationComparisonResult } from "../components/CitationComparisonResult";
import { demoManuscript, demoPaperClaims, demoCitationComparison } from "../data/mockData";
import { matchSelectionClaims, singleReferenceMarkers } from "../data/selectionClaims";
import { getLatestUploadedPaper } from "../data/workspacePapers";
import type { IdentifiedSource, PaperClaimsResponse, PaperRecord, CitationComparisonResponse } from "../types/api";

const demoClaimContext: Record<string, { heading: string; before: string; after: string }> = {
  "claim-attention": {
    heading: "2. Related Work",
    before: "Sequence modelling has traditionally relied on recurrent or convolutional architectures to represent dependencies between tokens.",
    after: "This architecture makes it possible to model long-range relationships while allowing substantially more parallel computation.",
  },
  "claim-bert": {
    heading: "3. Contextual Representation",
    before: "Pre-trained language models differ in how much surrounding context is available when a token representation is constructed.",
    after: "The resulting representations can then be fine-tuned for a wide range of downstream language understanding tasks.",
  },
  "claim-missing": {
    heading: "8. Limitations",
    before: "Automated checking may help authors discover mismatched references before a manuscript is submitted.",
    after: "However, the cited record must first be confirmed before this statement can be treated as evidence-backed.",
  },
};

function sourceMeta(source: IdentifiedSource) {
  return [source.authors.join(", "), source.venue, source.year].filter(Boolean).join(" · ");
}

export function VerifyPage({ example: initialExample = false, similarExample = false }: { example?: boolean; similarExample?: boolean }) {
  const [uploadedPaper] = useState(() => similarExample ? undefined : getLatestUploadedPaper("pdf"));
  const [example, setExample] = useState(initialExample && !uploadedPaper);
  const usingMockApi = example || configuredMockApi;
  const [searchParams] = useSearchParams();
  const requestedPaperId = searchParams.get("paper_id");
  const [papers, setPapers] = useState<PaperRecord[]>([]);
  const [selectedPaperId, setSelectedPaperId] = useState(requestedPaperId || uploadedPaper?.paperId || "");
  const [papersLoading, setPapersLoading] = useState(true);
  const [papersError, setPapersError] = useState<string | null>(null);
  const [paperPreviewReason, setPaperPreviewReason] = useState<string | null>(null);
  const [analysis, setAnalysis] = useState<PaperClaimsResponse | null>(null);
  const [selectedClaimId, setSelectedClaimId] = useState("");
  const [matchedClaimIds, setMatchedClaimIds] = useState<string[]>([]);
  const [selectedText, setSelectedText] = useState("");
  const [selectionError, setSelectionError] = useState("");
  const [bibPaperId, setBibPaperId] = useState("");
  const [bibliographies, setBibliographies] = useState<PaperRecord[]>([]);
  const [singleMarker, setSingleMarker] = useState("");
  const verifyController = useRef<AbortController | null>(null);
  const verifyVersion = useRef(0);
  const verifyBusy = useRef(false);
  const [analysisLoading, setAnalysisLoading] = useState(false);
  const [analysisError, setAnalysisError] = useState<string | null>(null);
  const [analysisPreviewReason, setAnalysisPreviewReason] = useState<string | null>(null);
  const [verifying, setVerifying] = useState(false);
  const [result, setResult] = useState<CitationComparisonResponse | null>(null);
  const [verifyError, setVerifyError] = useState<string | null>(null);
  const [readerView, setReaderView] = useState<"manuscript" | "source">("manuscript");
  const manuscriptDocumentRef = useRef<HTMLDivElement>(null);
  const citedDocumentRef = useRef<HTMLDivElement>(null);

  const loadPapers = useCallback(async (signal?: AbortSignal) => {
    if (example) {
      setPapers([demoManuscript]);
      setSelectedPaperId(demoManuscript.paper_id);
      setPapersLoading(false);
      return;
    }
    setPapersLoading(true);
    setPapersError(null);
    setPaperPreviewReason(null);
    try {
      const response = await listPapers(signal);
      if (signal?.aborted) return;
      const candidates = response.papers.filter((paper) => paper.file_type === "pdf");
      setPapers(candidates);
      setBibliographies(response.papers.filter((paper) => paper.file_type === "bib"));
      setSelectedPaperId((current) => {
        if (current && candidates.some((paper) => paper.paper_id === current)) return current;
        if (requestedPaperId && candidates.some((paper) => paper.paper_id === requestedPaperId)) return requestedPaperId;
        return candidates[0]?.paper_id || "";
      });
    } catch (error) {
      if (signal?.aborted) return;
      const message = error instanceof Error ? error.message : "Unable to load uploaded papers.";
      setPapersError(message);
    } finally {
      if (!signal?.aborted) setPapersLoading(false);
    }
  }, [requestedPaperId, example]);

  const loadAnalysis = useCallback(async (paper: PaperRecord, signal?: AbortSignal) => {
    verifyVersion.current += 1; verifyController.current?.abort();
    setSelectedText(""); setMatchedClaimIds([]); setSingleMarker(""); setVerifyError(null);
    if (example) {
      setAnalysis(demoPaperClaims);
      setSelectedClaimId("");
      setResult(null);
      return;
    }
    setAnalysisLoading(true);
    setAnalysisError(null);
    setAnalysisPreviewReason(null);
    setAnalysis(null);
    setSelectedClaimId("");
    setSingleMarker("");
    setResult(null);
    setVerifyError(null);
    try {
      const response = await getPaperClaims(paper.paper_id, signal, bibPaperId || undefined);
      if (signal?.aborted) return;
      setAnalysis(response);
      setSelectedClaimId("");
    } catch (error) {
      if (signal?.aborted) return;
      const message = error instanceof Error ? error.message : "Unable to load extracted claims.";
      setAnalysisError(message);
    } finally {
      if (!signal?.aborted) setAnalysisLoading(false);
    }
  }, [example, bibPaperId]);

  useEffect(() => {
    const controller = new AbortController();
    void loadPapers(controller.signal);
    return () => controller.abort();
  }, [loadPapers]);

  const selectedPaper = papers.find((paper) => paper.paper_id === selectedPaperId) || null;

  useEffect(() => {
    verifyVersion.current += 1;
    setSelectedText(""); setSelectionError(""); setSingleMarker(""); setMatchedClaimIds([]);
    setAnalysis(null);
    setReaderView("manuscript");
    setSelectedClaimId("");
    setSingleMarker("");
    setAnalysisError(null);
    setAnalysisPreviewReason(null);
    setAnalysisLoading(false);
    setResult(null);
    setVerifyError(null);
    if (!selectedPaper) return;
    if (selectedPaper.status !== "completed") {
      return;
    }
    const controller = new AbortController();
    void loadAnalysis(selectedPaper, controller.signal);
    return () => { controller.abort(); verifyVersion.current += 1; verifyController.current?.abort(); };
  }, [loadAnalysis, selectedPaper]);

  const selectedClaim = useMemo(
    () => analysis?.claims.find((claim) => claim.claim_id === selectedClaimId) || null,
    [analysis, selectedClaimId],
  );
  const matchedClaims = analysis?.claims.filter((claim) => matchedClaimIds.includes(claim.claim_id)) || [];
  const multipleSources = matchedClaims.length > 1;
  const needsCitationChoice = multipleSources && !selectedClaim;
  const markerOptions = selectedClaim ? singleReferenceMarkers(selectedClaim.citation_marker) : [];
  const citationMarker = markerOptions.length > 1 ? singleMarker : selectedClaim?.citation_marker || "";
  const displayedSource = result ? result.cited_source : selectedClaim?.cited_source;
  const displayedDocument = result ? result.source_document : selectedClaim?.source_document;
  const previewReason = [paperPreviewReason, analysisPreviewReason].filter(Boolean).join(" ");
  const verifyDisabledReason = analysisLoading ? "Loading citation information…"
    : !selectedText ? "Highlight a cited sentence in the manuscript first."
    : needsCitationChoice ? "Choose which citation to analyze."
    : !selectedClaim ? "Select a sentence with a citation returned for this manuscript."
    : !citationMarker ? "Choose one reference from this citation marker."
    : previewReason ? "Live verification is unavailable in this preview."
    : "";
  const canVerify = !verifyDisabledReason;
  const manuscriptContext = usingMockApi && selectedClaim ? demoClaimContext[selectedClaim.claim_id] : null;
  const reviewStatus = analysis?.status || selectedPaper?.status;
  const isProcessing = reviewStatus === "pending" || reviewStatus === "processing";
  const isFailed = reviewStatus === "failed";
  const isSearching = !result && selectedClaim?.resolution_status === "searching";

  const scrollToManuscriptMatch = useCallback(() => {
    const container = manuscriptDocumentRef.current;
    const match = container?.querySelector<HTMLElement>("[data-manuscript-match='true']");
    if (!container || !match) return;
    const top = match.getBoundingClientRect().top - container.getBoundingClientRect().top + container.scrollTop - 48;
    container.scrollTo({ top, behavior: "smooth" });
  }, []);

  const scrollToCitedMatch = useCallback(() => {
    const container = citedDocumentRef.current;
    const match = container?.querySelector<HTMLElement>("[data-review-source-match='true']");
    if (!container || !match) return;
    const top = match.getBoundingClientRect().top - container.getBoundingClientRect().top + container.scrollTop - 48;
    container.scrollTo({ top, behavior: "smooth" });
  }, []);

  const revealCitedArticle = useCallback(() => {
    setReaderView("source");
    window.setTimeout(() => {
      document.getElementById("review-cited-article")?.scrollIntoView({ behavior: "smooth", block: "nearest" });
      scrollToCitedMatch();
    }, 80);
  }, [scrollToCitedMatch]);

  useEffect(() => {
    const manuscriptTimer = window.setTimeout(scrollToManuscriptMatch, 80);
    return () => window.clearTimeout(manuscriptTimer);
  }, [scrollToManuscriptMatch, selectedClaim?.claim_id, readerView]);

  useEffect(() => {
    const timer = window.setTimeout(scrollToCitedMatch, 80);
    return () => window.clearTimeout(timer);
  }, [scrollToCitedMatch, selectedClaim?.claim_id, readerView]);

  function captureSelection() {
    if (verifying) return;
    const selection = window.getSelection();
    if (!selection || selection.isCollapsed || !selection.rangeCount) return;
    const range = selection.getRangeAt(0);
    const elementFor = (node: Node) => node.nodeType === Node.ELEMENT_NODE ? node as Element : node.parentElement;
    const start = elementFor(range.startContainer)?.closest<HTMLElement>("[data-selectable-paragraph]");
    const end = elementFor(range.endContainer)?.closest<HTMLElement>("[data-selectable-paragraph]");
    if (!start || !manuscriptDocumentRef.current?.contains(start)) return;
    verifyVersion.current += 1;
    setResult(null); setVerifyError(null); setSelectedClaimId(""); setSingleMarker(""); setMatchedClaimIds([]);
    const text = selection.toString().trim();
    if (start !== end || text.length > 4000) {
      setSelectedText(""); setSelectionError("Select one cited sentence within a paragraph (up to 4,000 characters).");
      return;
    }
    setSelectionError(""); setSelectedText(text);
    const matches = matchSelectionClaims(analysis?.claims || [], text, Number(start.dataset.page), Number(start.dataset.paragraph));
    setMatchedClaimIds(matches.map((claim) => claim.claim_id));
    if (matches.length === 1) {
      setSelectedClaimId(matches[0].claim_id);
    }
  }

  async function handleVerify() {
    if (!canVerify || !selectedClaim || verifyBusy.current) return;
    verifyBusy.current = true;
    const version = ++verifyVersion.current;
    const controller = new AbortController();
    verifyController.current = controller;
    setVerifying(true); setVerifyError(null); setResult(null);
    try {
      const request = { claim: selectedText, citation_marker: citationMarker, manuscript_id: selectedPaperId,
        claim_id: selectedClaim.claim_id, ...(bibPaperId ? { bib_paper_id: bibPaperId } : {}) };
      const response = example ? demoCitationComparison(request) : await verifyCitation(request, controller.signal);
      if (version === verifyVersion.current) setResult(response);
    } catch (error) {
      if (version === verifyVersion.current) setVerifyError(error instanceof Error ? error.message : "Verification failed.");
    } finally {
      verifyBusy.current = false; setVerifying(false);
    }
  }

  return (
    <div className="page-stack review-claims-page">
      <section className="page-heading heading-row">
        <div className="workspace-intro workspace-intro-evidence">
          <div className="workspace-intro-copy"><h1>Review claims</h1><p>Highlight a cited sentence, then analyze it.</p></div>
        </div>
        <div className="audit-heading-actions">
          <Link className="button button-secondary" to={example ? "/verify" : "/verify/example"}>{example ? "Back to my papers" : "Try example"}</Link>
          <UploadFilesButton pdfOnly disabled={verifying} onReady={async (paper) => {
            const response = await listPapers();
            setPapers(response.papers.filter((entry) => entry.file_type === "pdf"));
            setBibliographies(response.papers.filter((entry) => entry.file_type === "bib"));
            setPapersError(null);
            setPaperPreviewReason(null);
            setSelectedPaperId(paper.paper_id);
            setExample(false);
          }} />
          {bibliographies.length > 0 && <label className="manuscript-picker"><span>Bibliography</span><select aria-label="Bibliography" value={bibPaperId} disabled={verifying || papersLoading} onChange={(event) => { verifyVersion.current += 1; setResult(null); setSelectedText(""); setSelectedClaimId(""); setSingleMarker(""); setBibPaperId(event.target.value); }}><option value="">Manuscript references / automatic</option>{bibliographies.map((paper) => <option value={paper.paper_id} key={paper.paper_id} disabled={paper.status !== "completed"}>{paper.original_filename}</option>)}</select></label>}
          <label className="manuscript-picker"><span>Uploaded manuscript</span><select value={selectedPaperId} disabled={verifying || papersLoading || Boolean(papersError) || papers.length === 0} onChange={(event) => setSelectedPaperId(event.target.value)}>{papers.map((paper) => <option value={paper.paper_id} key={paper.paper_id}>{paper.title || paper.original_filename}</option>)}</select></label>
        </div>
      </section>

      {papersLoading && <section className="library-state panel" role="status"><span className="library-state-icon"><span className="spinner" /></span><h2>Loading uploaded manuscripts</h2><p>Reading completed papers from the backend.</p></section>}
      {!papersLoading && papersError && <section className="library-state library-error panel" role="alert"><span className="library-state-icon"><Icon name="x" /></span><h2>Couldn’t load uploaded manuscripts</h2><p>{papersError}</p><button className="button button-secondary" type="button" onClick={() => void loadPapers()}>Try again</button></section>}
      {!papersLoading && !papersError && papers.length === 0 && <section className="library-state panel"><span className="library-state-icon"><Icon name="document" /></span><h2>No uploaded manuscript</h2><p>No completed PDF manuscript is available from the backend.</p></section>}
      {example && <section className="review-example-guide panel"><div><span className="eyebrow">Interactive example</span><h2>Does the cited article support this sentence?</h2><p>On page 3, highlight “Self-attention enables the model…” with your mouse. Its source, Attention Is All You Need, appears automatically. Click Analyze selection to see a sample result.</p><small>This example uses prepared text and sample results. No backend analysis is performed.</small></div><button className="button button-secondary" type="button" onClick={() => { setReaderView("manuscript"); window.setTimeout(() => manuscriptDocumentRef.current?.querySelector('[data-page="3"][data-paragraph="1"]')?.scrollIntoView({ behavior: "smooth", block: "center" }), 0); }}>Find example sentence <Icon name="arrow" size={15} /></button></section>}
      {!papersLoading && !papersError && selectedPaper && (
        <>
        {isProcessing && <section className="audit-notice panel" role="status"><span className="spinner" /><div><strong>Manuscript is being processed</strong><p>Manuscript text will be available after parsing finishes.</p><button className="button button-secondary" type="button" onClick={() => void loadPapers()}>Refresh status</button></div></section>}
        {isFailed && <section className="library-state library-error panel" role="alert"><Icon name="x" /><h2>Parsing failed</h2><p>{analysis?.error_message || selectedPaper.error_message || "This PDF could not be parsed. Try uploading another file."}</p><button className="button button-secondary" type="button" onClick={() => void loadPapers()}>Refresh status</button></section>}
        {previewReason && <section className="analysis-preview-banner" role="status"><span><Icon name="spark" size={18} /></span><div><strong>Demo interface preview</strong><p>{previewReason}</p></div><button className="button button-secondary" type="button" onClick={() => void loadPapers()}>Check live analysis</button></section>}
        <section className="review-claims-grid">
          <div className="review-reading-column">
          <div className="reader-switch" role="group" aria-label="Choose document">
            <button type="button" aria-pressed={readerView === "manuscript"} onClick={() => setReaderView("manuscript")}><Icon name="document" size={16} /> Manuscript</button>
            <button type="button" aria-pressed={readerView === "source"} disabled={!selectedClaim || isSearching} onClick={() => setReaderView("source")}><Icon name="library" size={16} /> Cited source</button>
          </div>
          <article className="panel manuscript-panel" hidden={readerView !== "manuscript"}>
            <header className="manuscript-toolbar"><div><h2>Original manuscript</h2><p>{selectedPaper.original_filename}</p></div><span>{analysisLoading ? "Loading manuscript…" : usingMockApi || previewReason ? `Complete demo manuscript · ${analysis?.manuscript_document?.total_pages || 0} pages` : `Parsed manuscript · ${analysis?.manuscript_document?.total_pages || selectedPaper.pages} pages`}</span></header>
            <div className="claim-manuscript-scroll selection-manuscript" ref={manuscriptDocumentRef} onMouseUp={captureSelection} onKeyUp={captureSelection}>
              {analysisLoading && <div className="manuscript-loading"><span className="spinner" /><strong>Loading manuscript text…</strong></div>}
              {analysisError && !analysis && <div className="manuscript-loading error"><Icon name="x" /><strong>Original text unavailable</strong><p>{analysisError}</p><button className="button button-secondary" type="button" onClick={() => void loadAnalysis(selectedPaper)}>Try again</button></div>}
              {analysis?.manuscript_document?.pages.length ? analysis.manuscript_document.pages.map((page) => (
                <section className="manuscript-sheet" key={page.page}>
                  <small>{page.page} / {analysis.manuscript_document?.total_pages}</small>
                  {page.heading && <h2>{page.heading}</h2>}
                  {page.paragraphs.map((paragraph, paragraphIndex) => {
                    const matched = selectedClaim?.manuscript_location?.page === page.page
                      && selectedClaim?.manuscript_location?.paragraph_index === paragraphIndex;
                    return <p data-selectable-paragraph data-page={page.page} data-paragraph={paragraphIndex} className={matched ? "reviewed-claim-sentence" : ""} data-manuscript-match={matched ? "true" : undefined} tabIndex={matched ? 0 : undefined} title={matched ? "Claim extracted from this sentence" : undefined} key={`${page.page}-${paragraphIndex}`}>{paragraph}</p>;
                  })}
                </section>
              )) : analysis?.status === "completed" && selectedClaim && (
                <section className="manuscript-sheet claim-manuscript-sheet">
                  <small>{selectedClaim.page ? `Page ${selectedClaim.page}` : "Extracted text"}</small>
                  <h2>{manuscriptContext?.heading || "Extracted manuscript claim"}</h2>
                  {manuscriptContext?.before && <p>{manuscriptContext.before}</p>}
                  <p data-selectable-paragraph className="reviewed-claim-sentence">{selectedClaim.text} <mark>{selectedClaim.citation_marker}</mark></p>
                  {manuscriptContext?.after && <p>{manuscriptContext.after}</p>}
                  {!usingMockApi && !previewReason && <aside className="manuscript-callouts"><span>Exact claim returned by the analysis API</span></aside>}
                </section>
              )}
              {!analysisLoading && !analysisError && !analysis?.manuscript_document?.pages.length && !selectedClaim && <div className="manuscript-loading"><Icon name="document" /><strong>{isProcessing ? "Waiting for parsed text…" : isFailed ? "Original text unavailable because parsing failed" : "No manuscript text was returned"}</strong></div>}
            </div>
          </article>

        {selectedClaim && !isSearching && (
          <section className="panel review-citation-source" id="review-cited-article" hidden={readerView !== "source"}>
            <header className="manuscript-toolbar citation-source-toolbar">
              <div><h2>Cited article — original text</h2><p>{displayedSource?.title || "Citation article not identified"}</p></div>
              <div>
                <span>{displayedDocument ? usingMockApi || previewReason ? "Demo cited document" : `${displayedDocument.total_pages} pages` : displayedSource ? "Original text unavailable" : "Source not found"}</span>
                {displayedDocument?.matched_location && <button className="button button-secondary" type="button" onClick={scrollToCitedMatch}><Icon name="search" size={14} /> Jump to matched passage</button>}
              </div>
            </header>
            {displayedDocument ? (
              <div className="manuscript-scroll citation-source-scroll" ref={citedDocumentRef}>
                {displayedDocument.pages.map((page) => (
                  <section className="manuscript-sheet citation-source-sheet" key={page.page}>
                    <small>{page.page} / {displayedDocument?.total_pages}</small>
                    {page.heading && <h2>{page.heading}</h2>}
                    {page.paragraphs.map((paragraph, paragraphIndex) => {
                      const matched = displayedDocument?.matched_location?.page === page.page
                        && displayedDocument.matched_location.paragraph_index === paragraphIndex;
                      return <p className={matched ? "matched-source-paragraph" : ""} data-review-source-match={matched ? "true" : undefined} key={`${page.page}-${paragraphIndex}`}>{paragraph}{matched && <mark>ClaimTrace matched passage · Page {page.page}, paragraph {paragraphIndex + 1}</mark>}</p>;
                    })}
                  </section>
                ))}
              </div>
            ) : (
              <div className="review-source-unavailable">
                <span><Icon name={displayedSource ? "document" : "search"} size={22} /></span>
                <div><strong>{displayedSource ? "Cited article text was not returned" : "Cited article not confirmed"}</strong><p>{displayedSource ? "The bibliographic record is available, but its original text has not been returned." : "No exact record has been confirmed, so there is no confirmed source text to display."}</p></div>
              </div>
            )}
          </section>
        )}
          </div>

          <aside className="panel citation-resolution-panel">
            <div className="citation-resolution-heading"><div><h2>Selected citation</h2><p>Drag over a cited sentence in the manuscript, then click Analyze selection.</p></div></div>
            <div className="selected-citation-text" role="status">{selectedText ? <blockquote>{selectedText}</blockquote> : <p>No text selected yet. Include the citation marker when highlighting a sentence.</p>}</div>
            {selectionError && <p className="inline-error" role="alert">{selectionError}</p>}
            {selectedText && multipleSources && <label className="field claim-picker-field"><span>Cited source</span><select aria-label="Cited source" value={selectedClaimId} disabled={verifying} onChange={(event) => { setSelectedClaimId(event.target.value); setSingleMarker(""); setResult(null); setVerifyError(null); }}><option value="" disabled>Choose which citation to analyze…</option>{matchedClaims.map((claim) => <option value={claim.claim_id} key={claim.claim_id}>{claim.citation_marker} · {claim.cited_source?.title || "Source not identified"}</option>)}</select><small>This selection contains multiple citations. Choose one to analyze.</small></label>}
            {selectedClaim && markerOptions.length > 1 && <label className="field claim-picker-field"><span>Reference in citation</span><select aria-label="Reference in citation" value={singleMarker} disabled={verifying} onChange={(event) => { setSingleMarker(event.target.value); setResult(null); setVerifyError(null); }}><option value="" disabled>Choose one reference…</option>{markerOptions.map((marker) => <option key={marker} value={marker}>{marker}</option>)}</select></label>}
            {selectedText && !selectedClaim && !needsCitationChoice && <p className="selection-source-unlinked" role="status">This selection is not linked to an extracted citation. Highlight the cited sentence and its marker.</p>}
            {selectedClaim && !result && <>
              <section className={`citation-existence ${isSearching ? "searching" : displayedSource ? "exists" : "missing"}`} role="status"><span><Icon name={displayedSource ? "document" : "search"} size={18} /></span><div><strong>{displayedSource ? "Associated reference" : "Source resolution pending"}</strong><p>{selectedClaim.resolution_message || "Analyze this citation to resolve its source and attempt a comparison. No judgement has been made yet."}</p></div></section>
              {displayedSource && <section className="database-source-card interactive-source-card" role="button" tabIndex={0} title="Open this article's original text" onClick={revealCitedArticle} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); revealCitedArticle(); } }}><div className="automatic-field-label"><span>Cited source</span><small>Click to open original text</small></div><strong>{displayedSource.title}</strong><p>{sourceMeta(displayedSource)}</p><footer><code>{displayedSource.citation_key}</code>{displayedSource.url && <a href={displayedSource.url} target="_blank" rel="noreferrer" onClick={(event) => event.stopPropagation()}>Open record <Icon name="external" size={14} /></a>}</footer></section>}
              {Boolean(selectedClaim.similar_sources?.length) && <section className="similar-source-section"><h3>Possible sources</h3><p>These candidates are unconfirmed. Citation analysis resolves the source; manual source overrides are not supported.</p>{selectedClaim.similar_sources?.map((source) => <div className="database-source-card" key={source.citation_key}><strong>{source.title}</strong><p>{sourceMeta(source)}</p>{source.url && <a href={source.url} target="_blank" rel="noreferrer">Open candidate record</a>}</div>)}</section>}
            </>}

            {verifyError && <div className="inline-error" role="alert">{verifyError}</div>}
            <button className="button button-primary full-button" type="button" disabled={!canVerify || verifying} aria-describedby={verifyDisabledReason ? "verify-disabled-reason" : undefined} onClick={() => void handleVerify()}>{verifying ? <><span className="spinner" /> Analyzing…</> : <><Icon name="verify" size={17} /> Analyze selection</>}</button>

            {verifyDisabledReason && <p className="verify-action-hint" id="verify-disabled-reason" role="status">{verifyDisabledReason}</p>}

            {result && <CitationComparisonResult result={result} demo={usingMockApi} />}
          </aside>
        </section>


        </>
      )}
    </div>
  );
}
