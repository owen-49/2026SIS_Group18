import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { getPaperClaims, listPapers, usingMockApi, verifyClaim } from "../api/client";
import { Icon } from "../components/Icon";
import { VerdictBadge } from "../components/VerdictBadge";
import { demoManuscript, demoPaperClaims } from "../data/mockData";
import { getWorkspacePapers } from "../data/workspacePapers";
import type { IdentifiedSource, PaperClaimsResponse, PaperRecord, VerifyResponse } from "../types/api";

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

export function VerifyPage() {
  const [searchParams] = useSearchParams();
  const requestedPaperId = searchParams.get("paper_id");
  const [papers, setPapers] = useState<PaperRecord[]>([]);
  const [selectedPaperId, setSelectedPaperId] = useState("");
  const [papersLoading, setPapersLoading] = useState(true);
  const [papersError, setPapersError] = useState<string | null>(null);
  const [paperPreviewReason, setPaperPreviewReason] = useState<string | null>(null);
  const [analysis, setAnalysis] = useState<PaperClaimsResponse | null>(null);
  const [selectedClaimId, setSelectedClaimId] = useState("");
  const [selectedCandidateId, setSelectedCandidateId] = useState("");
  const [analysisLoading, setAnalysisLoading] = useState(false);
  const [analysisError, setAnalysisError] = useState<string | null>(null);
  const [analysisPreviewReason, setAnalysisPreviewReason] = useState<string | null>(null);
  const [verifying, setVerifying] = useState(false);
  const [result, setResult] = useState<VerifyResponse | null>(null);
  const [verifyError, setVerifyError] = useState<string | null>(null);
  const manuscriptDocumentRef = useRef<HTMLDivElement>(null);
  const citedDocumentRef = useRef<HTMLDivElement>(null);

  const loadPapers = useCallback(async (signal?: AbortSignal) => {
    setPapersLoading(true);
    setPapersError(null);
    setPaperPreviewReason(null);
    try {
      const response = await listPapers(signal);
      if (signal?.aborted) return;
      const candidates = response.papers.filter((paper) => paper.file_type === "pdf");
      setPapers(candidates);
      setSelectedPaperId((current) => {
        if (current && candidates.some((paper) => paper.paper_id === current)) return current;
        if (requestedPaperId && candidates.some((paper) => paper.paper_id === requestedPaperId)) return requestedPaperId;
        return candidates[0]?.paper_id || "";
      });
    } catch (error) {
      if (signal?.aborted) return;
      const message = error instanceof Error ? error.message : "Unable to load uploaded papers.";
      const localPaper = getWorkspacePapers()[0];
      const previewPaper: PaperRecord = {
        ...demoManuscript,
        paper_id: localPaper.paperId,
        original_filename: localPaper.fileName,
        title: localPaper.fileName.replace(/\.pdf$/i, "").replace(/[-_]+/g, " "),
      };
      setPapers([previewPaper]);
      setSelectedPaperId(previewPaper.paper_id);
      setPapersError(null);
      setPaperPreviewReason(`The Paper Library API is unavailable (${message}). Showing a labelled interface preview using local upload metadata.`);
    } finally {
      if (!signal?.aborted) setPapersLoading(false);
    }
  }, [requestedPaperId]);

  const loadAnalysis = useCallback(async (paper: PaperRecord, signal?: AbortSignal) => {
    setAnalysisLoading(true);
    setAnalysisError(null);
    setAnalysisPreviewReason(null);
    setAnalysis(null);
    setSelectedClaimId("");
    setSelectedCandidateId("");
    setResult(null);
    setVerifyError(null);
    try {
      const response = await getPaperClaims(paper.paper_id, signal);
      if (signal?.aborted) return;
      setAnalysis(response);
      setSelectedClaimId(response.status === "completed" ? response.claims[0]?.claim_id || "" : "");
    } catch (error) {
      if (signal?.aborted) return;
      const message = error instanceof Error ? error.message : "Unable to load extracted claims.";
      setAnalysisError(message);
      setAnalysis({ ...demoPaperClaims, manuscript_id: paper.paper_id });
      setSelectedClaimId(demoPaperClaims.claims[0]?.claim_id || "");
      setAnalysisPreviewReason(`Live claim analysis is unavailable (${message}). Showing clearly labelled demo content for interface review.`);
    } finally {
      if (!signal?.aborted) setAnalysisLoading(false);
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void loadPapers(controller.signal);
    return () => controller.abort();
  }, [loadPapers]);

  const selectedPaper = papers.find((paper) => paper.paper_id === selectedPaperId) || null;

  useEffect(() => {
    setAnalysis(null);
    setSelectedClaimId("");
    setSelectedCandidateId("");
    setAnalysisError(null);
    setAnalysisPreviewReason(null);
    setAnalysisLoading(false);
    setResult(null);
    setVerifyError(null);
    if (!selectedPaper) return;
    if (selectedPaper.status !== "completed") {
      setAnalysis({ ...demoPaperClaims, manuscript_id: selectedPaper.paper_id });
      setSelectedClaimId(demoPaperClaims.claims[0]?.claim_id || "");
      setAnalysisPreviewReason(`This uploaded manuscript is ${selectedPaper.status}; live claims are not available yet. Showing demo content for interface review only.`);
      return;
    }
    const controller = new AbortController();
    void loadAnalysis(selectedPaper, controller.signal);
    return () => controller.abort();
  }, [loadAnalysis, selectedPaper]);

  const selectedClaim = useMemo(
    () => analysis?.claims.find((claim) => claim.claim_id === selectedClaimId) || null,
    [analysis, selectedClaimId],
  );
  const selectedCandidate = selectedClaim?.similar_sources?.find((source) => source.source_paper_id === selectedCandidateId) || null;
  const comparisonSource = selectedClaim?.cited_source || selectedCandidate;
  const previewReason = [paperPreviewReason, analysisPreviewReason].filter(Boolean).join(" ");
  const canVerify = Boolean(selectedClaim && comparisonSource?.source_paper_id && !previewReason);
  const manuscriptContext = selectedClaim ? demoClaimContext[selectedClaim.claim_id] : null;

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
    document.getElementById("review-cited-article")?.scrollIntoView({ behavior: "smooth", block: "start" });
    window.setTimeout(scrollToCitedMatch, 420);
  }, [scrollToCitedMatch]);

  useEffect(() => {
    const manuscriptTimer = window.setTimeout(scrollToManuscriptMatch, 80);
    return () => window.clearTimeout(manuscriptTimer);
  }, [scrollToManuscriptMatch, selectedClaim?.claim_id]);

  useEffect(() => {
    const timer = window.setTimeout(scrollToCitedMatch, 80);
    return () => window.clearTimeout(timer);
  }, [scrollToCitedMatch, selectedClaim?.claim_id]);

  function chooseClaim(claimId: string) {
    setSelectedClaimId(claimId);
    setSelectedCandidateId("");
    setResult(null);
    setVerifyError(null);
  }

  async function handleVerify() {
    if (!selectedClaim || !comparisonSource?.source_paper_id) return;
    setVerifying(true);
    setVerifyError(null);
    setResult(null);
    try {
      setResult(await verifyClaim(selectedClaim.text, comparisonSource.source_paper_id));
    } catch (error) {
      setVerifyError(error instanceof Error ? error.message : "Verification failed.");
    } finally {
      setVerifying(false);
    }
  }

  return (
    <div className="page-stack review-claims-page">
      <section className="page-heading heading-row">
        <div><span className="eyebrow">Automatic citation trace</span><h1>Review claims</h1><p>Read the uploaded manuscript on the left and confirm the database-identified citation on the right.</p></div>
        <label className="manuscript-picker"><span>Uploaded manuscript</span><select value={selectedPaperId} disabled={papersLoading || Boolean(papersError) || papers.length === 0} onChange={(event) => setSelectedPaperId(event.target.value)}>{papers.map((paper) => <option value={paper.paper_id} key={paper.paper_id}>{paper.title || paper.original_filename}</option>)}</select></label>
      </section>

      {papersLoading && <section className="library-state panel" role="status"><span className="library-state-icon"><span className="spinner" /></span><h2>Loading uploaded manuscripts</h2><p>Reading papers from your Paper Library.</p></section>}
      {!papersLoading && papersError && <section className="library-state library-error panel" role="alert"><span className="library-state-icon"><Icon name="x" /></span><h2>Couldn’t load uploaded manuscripts</h2><p>{papersError}</p><button className="button button-secondary" type="button" onClick={() => void loadPapers()}>Try again</button></section>}
      {!papersLoading && !papersError && papers.length === 0 && <section className="library-state panel"><span className="library-state-icon"><Icon name="document" /></span><h2>No uploaded manuscript</h2><p>Add a PDF in Paper Library before reviewing its claims.</p><Link className="button button-primary" to="/library?upload=1">Upload a paper</Link></section>}
      {!papersLoading && !papersError && selectedPaper && (
        <>
        {previewReason && <section className="analysis-preview-banner" role="status"><span><Icon name="spark" size={18} /></span><div><strong>Demo interface preview</strong><p>{previewReason}</p></div><button className="button button-secondary" type="button" onClick={() => void loadPapers()}>Check live analysis</button></section>}
        <section className="review-claims-grid">
          <article className="panel manuscript-panel">
            <header className="manuscript-toolbar"><div><h2>Original manuscript</h2><p>{selectedPaper.original_filename}</p></div><span>{analysisLoading ? "Loading manuscript…" : usingMockApi || previewReason ? `Complete demo manuscript · ${analysis?.manuscript_document?.total_pages || 0} pages` : `Parsed manuscript · ${analysis?.manuscript_document?.total_pages || selectedPaper.pages} pages`}</span></header>
            <div className="claim-manuscript-scroll" ref={manuscriptDocumentRef}>
              {analysisLoading && <div className="manuscript-loading"><span className="spinner" /><strong>Extracting claims and citation markers…</strong></div>}
              {analysisError && !analysis && <div className="manuscript-loading error"><Icon name="x" /><strong>Original text unavailable</strong><p>{analysisError}</p><button className="button button-secondary" type="button" onClick={() => void loadAnalysis(selectedPaper)}>Try again</button></div>}
              {analysis?.status === "completed" && selectedClaim && analysis.manuscript_document ? analysis.manuscript_document.pages.map((page) => (
                <section className="manuscript-sheet" key={page.page}>
                  <small>{page.page} / {analysis.manuscript_document?.total_pages}</small>
                  {page.heading && <h2>{page.heading}</h2>}
                  {page.paragraphs.map((paragraph, paragraphIndex) => {
                    const matched = selectedClaim.manuscript_location?.page === page.page
                      && selectedClaim.manuscript_location.paragraph_index === paragraphIndex;
                    return <p className={matched ? "reviewed-claim-sentence" : ""} data-manuscript-match={matched ? "true" : undefined} tabIndex={matched ? 0 : undefined} title={matched ? "Claim extracted from this sentence" : undefined} key={`${page.page}-${paragraphIndex}`}>{paragraph}{matched && <> <mark>{selectedClaim.citation_marker}</mark></>}</p>;
                  })}
                </section>
              )) : analysis?.status === "completed" && selectedClaim && (
                <section className="manuscript-sheet claim-manuscript-sheet">
                  <small>{selectedClaim.page ? `Page ${selectedClaim.page}` : "Extracted text"}</small>
                  <h2>{manuscriptContext?.heading || "Extracted manuscript claim"}</h2>
                  {manuscriptContext?.before && <p>{manuscriptContext.before}</p>}
                  <p className="reviewed-claim-sentence">{selectedClaim.text} <mark>{selectedClaim.citation_marker}</mark></p>
                  {manuscriptContext?.after && <p>{manuscriptContext.after}</p>}
                  {!usingMockApi && !previewReason && <aside className="manuscript-callouts"><span>Exact claim returned by the analysis API</span></aside>}
                </section>
              )}
              {analysis?.status === "completed" && analysis.claims.length === 0 && <div className="manuscript-loading"><Icon name="search" /><strong>No cited claims found</strong></div>}
            </div>
          </article>

          <aside className="panel citation-resolution-panel">
            <div className="citation-resolution-heading"><div><h2>Citation identification</h2><p>Select a claim to inspect whether its cited article exists.</p></div>{analysis?.claims && <span>{analysis.claims.length} claims</span>}</div>

            {analysis?.status === "completed" && analysis.claims.length > 0 && <label className="field claim-picker-field"><span>Claim in manuscript</span><select value={selectedClaimId} onChange={(event) => chooseClaim(event.target.value)}>{analysis.claims.map((claim, index) => <option value={claim.claim_id} key={claim.claim_id}>{index + 1}. {claim.text}</option>)}</select></label>}

            {selectedClaim && (
              <>
                <section className={`citation-existence ${selectedClaim.cited_source ? "exists" : "missing"}`}><span><Icon name={selectedClaim.cited_source ? "check" : "x"} size={18} /></span><div><strong>{selectedClaim.cited_source ? "Cited article found" : "Cited article not found"}</strong><p>{selectedClaim.cited_source ? `Identified by ${selectedClaim.cited_source.database || "the academic database"}.` : "No exact bibliographic record was confirmed in the connected academic databases."}</p></div></section>

                {selectedClaim.cited_source && <section className="database-source-card interactive-source-card" role="button" tabIndex={0} title="Open this article's original text" onClick={revealCitedArticle} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); revealCitedArticle(); } }}><div className="automatic-field-label"><span>Database-identified article</span><small>Click to open original text</small></div><strong>{selectedClaim.cited_source.title}</strong><p>{sourceMeta(selectedClaim.cited_source)}</p><footer><code>{selectedClaim.cited_source.citation_key}</code>{selectedClaim.cited_source.url && <a href={selectedClaim.cited_source.url} target="_blank" rel="noreferrer" onClick={(event) => event.stopPropagation()}>Open record <Icon name="external" size={14} /></a>}</footer></section>}

                {!selectedClaim.cited_source && (
                  <section className="similar-source-section">
                    <div><h3>Similar articles</h3><p>Select an optional candidate to compare with the claim. This does not replace or confirm the missing citation.</p></div>
                    {selectedClaim.similar_sources?.length ? <div className="similar-source-list">{selectedClaim.similar_sources.map((source) => <label className={selectedCandidateId === source.source_paper_id ? "similar-source-option selected" : "similar-source-option"} key={source.source_paper_id || source.citation_key}><input type="radio" name="similar-source" checked={selectedCandidateId === source.source_paper_id} onChange={() => { setSelectedCandidateId(source.source_paper_id || ""); setResult(null); }} /><span><strong>{source.title}</strong><small>{sourceMeta(source)}</small><em>{Math.round(source.similarity * 100)}% title/metadata similarity</em></span></label>)}</div> : <div className="no-similar-sources">No similar database records were returned.</div>}
                  </section>
                )}

                {verifyError && <div className="inline-error">{verifyError}</div>}
                <button className="button button-primary full-button" type="button" disabled={!canVerify || verifying} onClick={() => void handleVerify()}>{verifying ? <><span className="spinner" /> Comparing…</> : previewReason ? <><Icon name="shield" size={17} /> Demo preview — live verification unavailable</> : <><Icon name="verify" size={17} />{selectedClaim.cited_source ? "Compare with cited article" : "Compare with selected candidate"}</>}</button>
              </>
            )}

            {result && <section className="claim-comparison-result"><div className="comparison-result-heading"><span><small>AI comparison</small><VerdictBadge verdict={result.verdict} /></span><strong>{Math.round(result.confidence * 100)}%</strong></div><p>{result.rationale}</p>{result.matches.map((match, index) => <blockquote key={index}>“{match.passage_text}”<footer>{Math.round(match.similarity * 100)}% semantic match</footer></blockquote>)}{!selectedClaim?.cited_source && <small className="candidate-warning">Candidate comparison only — the manuscript’s cited article remains unverified.</small>}</section>}
          </aside>
        </section>

        {selectedClaim && (
          <section className="panel review-citation-source" id="review-cited-article">
            <header className="manuscript-toolbar citation-source-toolbar">
              <div><h2>Cited article — original text</h2><p>{selectedClaim.cited_source?.title || "Citation article not identified"}</p></div>
              <div>
                <span>{selectedClaim.source_document ? usingMockApi || previewReason ? "Demo cited document" : `${selectedClaim.source_document.total_pages} pages` : selectedClaim.cited_source ? "Original text unavailable" : "Source not found"}</span>
                {selectedClaim.source_document?.matched_location && <button className="button button-secondary" type="button" onClick={scrollToCitedMatch}><Icon name="search" size={14} /> Jump to matched passage</button>}
              </div>
            </header>
            {selectedClaim.source_document ? (
              <div className="manuscript-scroll citation-source-scroll" ref={citedDocumentRef}>
                {selectedClaim.source_document.pages.map((page) => (
                  <section className="manuscript-sheet citation-source-sheet" key={page.page}>
                    <small>{page.page} / {selectedClaim.source_document?.total_pages}</small>
                    {page.heading && <h2>{page.heading}</h2>}
                    {page.paragraphs.map((paragraph, paragraphIndex) => {
                      const matched = selectedClaim.source_document?.matched_location?.page === page.page
                        && selectedClaim.source_document.matched_location.paragraph_index === paragraphIndex;
                      return <p className={matched ? "matched-source-paragraph" : ""} data-review-source-match={matched ? "true" : undefined} key={`${page.page}-${paragraphIndex}`}>{paragraph}{matched && <mark>ClaimTrace matched passage · Page {page.page}, paragraph {paragraphIndex + 1}</mark>}</p>;
                    })}
                  </section>
                ))}
              </div>
            ) : (
              <div className="review-source-unavailable">
                <span><Icon name={selectedClaim.cited_source ? "document" : "search"} size={22} /></span>
                <div><strong>{selectedClaim.cited_source ? "Cited article text was not returned" : "Cited article not found"}</strong><p>{selectedClaim.cited_source ? "The analysis API identified the bibliographic record but did not provide source_document pages. Full original text cannot be displayed yet." : "No exact academic database record exists for this citation, so there is no confirmed original article to display."}</p></div>
              </div>
            )}
          </section>
        )}
        </>
      )}
    </div>
  );
}
