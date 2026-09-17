import { useEffect, useMemo, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { listPapers, runAudit, usingMockApi as configuredMockApi } from "../api/client";
import { Icon } from "../components/Icon";
import { PaperManager } from "../components/PaperManager";
import { demoAudit, demoManuscript } from "../data/mockData";
import { titleOverlap } from "../data/referenceSimilarity";
import { getLatestUploadedPaper, getWorkspacePapers } from "../data/workspacePapers";
import type { AuditResult, AuditResponse, AuditStatus, PaperRecord } from "../types/api";

type Filter = "ALL" | AuditStatus;
interface AuditLocationState { paperId?: string }

const statusLabels: Record<AuditStatus, string> = {
  VERIFIED: "Verified", METADATA_MISMATCH: "Metadata mismatch", NEEDS_REVIEW: "Needs review",
  NOT_FOUND: "Not found", LOOKUP_FAILED: "Lookup failed",
};
const filterOptions: Array<{ value: Filter; label: string }> = [
  { value: "ALL", label: "All references" },
  ...Object.entries(statusLabels).map(([value, label]) => ({ value: value as AuditStatus, label })),
];

function tone(status: AuditStatus) {
  if (status === "VERIFIED") return "success";
  if (status === "METADATA_MISMATCH" || status === "NEEDS_REVIEW") return "warning";
  return "danger";
}
function title(result: AuditResult) { return result.entry.metadata.title || result.entry.metadata.raw_text || result.entry.entry_id; }
function meta(result: AuditResult) {
  const value = result.entry.metadata;
  return [value.authors.join(", "), value.venue, value.year].filter(Boolean).join(" · ") || "No structured metadata extracted";
}

export function AuditPage({ example: initialExample = false, similarExample = false }: { example?: boolean; similarExample?: boolean }) {
  const [uploadedPaper] = useState(() => similarExample ? undefined : getLatestUploadedPaper());
  const [example, setExample] = useState(initialExample && !uploadedPaper);
  const usingMockApi = example || configuredMockApi;
  const location = useLocation();
  const locationState = location.state as AuditLocationState | null;
  const demoPapers = useMemo<PaperRecord[]>(() => example ? [demoManuscript] : getWorkspacePapers().map((paper) => ({
    paper_id: paper.paperId, original_filename: paper.fileName, file_type: paper.fileType || "pdf",
    file_size: paper.fileSize || 0, status: paper.status || "completed", pages: paper.pages || 0,
    paragraph_count: paper.paragraphCount || 0, entry_count: paper.entryCount || 0,
    title: paper.fileName.replace(/\.(pdf|bib)$/i, ""), error_message: null,
    created_at: String(paper.uploadedAt || ""), updated_at: String(paper.uploadedAt || ""),
  })), [example]);
  const [papers, setPapers] = useState<PaperRecord[]>(usingMockApi ? demoPapers : []);
  const [paperId, setPaperId] = useState(locationState?.paperId || uploadedPaper?.paperId || (usingMockApi ? demoPapers[0]?.paper_id || "" : ""));
  const [audit, setAudit] = useState<AuditResponse | null>(usingMockApi ? demoAudit : null);
  const [selectedId, setSelectedId] = useState(usingMockApi ? similarExample ? "attention-incomplete" : demoAudit.results[0]?.entry.entry_id || "" : "");
  const [filter, setFilter] = useState<Filter>("ALL");
  const [query, setQuery] = useState("");
  const [papersLoading, setPapersLoading] = useState(!usingMockApi);
  const [loading, setLoading] = useState(false);
  const [papersError, setPapersError] = useState<string | null>(null);
  const [auditError, setAuditError] = useState<string | null>(null);

  const [papersVersion, setPapersVersion] = useState(0);
  const [papersOpen, setPapersOpen] = useState(false);
  const papersDialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    if (papersOpen) papersDialog.current?.showModal();
    else papersDialog.current?.close();
  }, [papersOpen]);
  useEffect(() => {
    if (example) return;
    setPapersLoading(true); setPapersError(null);
    const controller = new AbortController();
    listPapers(controller.signal).then((response) => {
      if (controller.signal.aborted) return;
      const completed = response.papers.filter((paper) => paper.status === "completed");
      setPapers(response.papers);
      setPaperId((current) => completed.some((paper) => paper.paper_id === current) ? current : "");
    }).catch((error: unknown) => {
      if (!controller.signal.aborted) setPapersError(error instanceof Error ? error.message : "Unable to load uploaded files.");
    }).finally(() => { if (!controller.signal.aborted) setPapersLoading(false); });
    return () => controller.abort();
  }, [usingMockApi, example, papersVersion]);

  const completedPapers = papers.filter((paper) => paper.status === "completed");
  const currentPaper = completedPapers.find((paper) => paper.paper_id === paperId);
  useEffect(() => {
    if (usingMockApi) return;
    setAudit(null); setSelectedId(""); setAuditError(null);
  }, [paperId, usingMockApi]);

  async function refreshAudit() {
    if (!currentPaper) return;
    setLoading(true); setAuditError(null);
    try {
      const response = example ? demoAudit : await runAudit(currentPaper.paper_id, currentPaper.file_type);
      setAudit(response); setSelectedId(response.results[0]?.entry.entry_id || "");
    } catch (error) {
      setAuditError(error instanceof Error ? error.message : "Unable to run the bibliography audit.");
    } finally { setLoading(false); }
  }

  const results = useMemo(() => (audit?.results || []).filter((result) => {
    const value = query.trim().toLowerCase();
    const searchable = `${title(result)} ${result.entry.entry_id} ${meta(result)}`.toLowerCase();
    return (filter === "ALL" || result.status === filter) && (!value || searchable.includes(value));
  }), [audit, filter, query]);
  const selected = results.find((result) => result.entry.entry_id === selectedId) || results[0] || null;
  const verified = audit?.counts.VERIFIED || 0;
  const verifiedPercentage = audit?.total_entries ? Math.round(verified / audit.total_entries * 100) : 0;
  const summaryText = !audit?.total_entries
    ? "No references were extracted. Review the PDF reference list before trying again."
    : audit.total_entries - verified
      ? `${audit.total_entries - verified} references need attention.`
      : "All checked references matched their publication records.";

  return <div className="page-stack audit-review-page">
    <section className="page-heading heading-row">
      <div className="workspace-intro">
        <div className="workspace-intro-copy"><h1>Batch audit</h1><p>Check references and metadata.</p></div>
      </div>
    </section>

    <div className="audit-library-toolbar">
      <button className="manage-papers-entry" type="button" aria-haspopup="dialog" aria-expanded={papersOpen} aria-controls="audit-paper-manager" onClick={() => setPapersOpen(true)}><Icon name="folder" size={17} /> Manage papers</button>
    </div>

    <section className={`audit-input-card${currentPaper ? " has-paper" : ""}`} aria-label="Current audit paper">
      <div className="audit-input-document"><span className="audit-input-icon"><Icon name="document" size={24} /></span><div><span className="eyebrow">{currentPaper ? "Selected for audit" : "Start an audit"}</span><h2>{papersLoading ? "Loading your papers…" : currentPaper?.original_filename || "Choose a paper to begin"}</h2><p>{currentPaper ? `${currentPaper.file_type === "bib" ? "BibTeX bibliography" : "PDF manuscript"} · Ready to check references` : "Select a PDF or bibliography in Manage papers."}</p></div></div>
      <button className="button button-primary audit-run-button" type="button" disabled={loading || papersLoading || !currentPaper} onClick={() => void refreshAudit()}>{loading ? <><span className="spinner" /> Auditing…</> : <><Icon name="audit" size={17} /> Run audit</>}</button>
    </section>
    {!papersOpen && papersError && <p className="paper-manager-message paper-manager-error" role="alert">{papersError} Open Manage papers to retry.</p>}

    <dialog id="audit-paper-manager" className="paper-manager-dialog" ref={papersDialog} aria-labelledby="paper-manager-title" onClose={(event) => { if (event.target === event.currentTarget) setPapersOpen(false); }}>
    <PaperManager onClose={() => setPapersOpen(false)} papers={papers} selectedId={paperId} loading={papersLoading} busy={loading}
      error={papersError} demo={usingMockApi} onRefresh={() => { setExample(false); setPapersVersion((value) => value + 1); }}
      onSelect={(id) => { setPaperId(id); setAudit(null); setSelectedId(""); setAuditError(null); setPapersOpen(false); }}
      onDeleted={(id) => {
        setPapers((current) => current.filter((paper) => paper.paper_id !== id));
        if (id === paperId) { setPaperId(""); setAudit(null); setSelectedId(""); setAuditError(null); }
      }}
      onReady={async (paper) => {
        const response = await listPapers();
        setPapers(response.papers); setPapersError(null); setPaperId(paper.paper_id);
        setAudit(null); setSelectedId(""); setExample(false);
      }} />
    </dialog>
    {auditError && <section className="library-state library-error panel" role="alert"><span className="library-state-icon"><Icon name="x" /></span><h2>Audit could not be completed</h2><p>{auditError}</p></section>}

    {audit && <>
      {audit.warnings.map((warning) => <section className="audit-notice panel" key={warning}><Icon name="document" size={17} /><div><strong>Audit warning</strong><p>{warning}</p></div></section>)}
      <section className="audit-summary panel">
        <div className="audit-score"><div className="score-ring" style={{ background: `radial-gradient(circle at center,#fff 57%,transparent 58%), conic-gradient(#13846d 0 ${verifiedPercentage}%,#e6eeeb ${verifiedPercentage}%)` }}><strong>{verifiedPercentage}</strong><small>% verified</small></div><div><span className="eyebrow">{currentPaper?.original_filename || audit.input_paper_id}</span><h2>{audit.total_entries} references checked</h2><p>{summaryText}</p></div></div>
        <div className="audit-count-grid">{Object.entries(statusLabels).map(([status, label]) => <div key={status}><strong>{audit.counts[status as AuditStatus] || 0}</strong><span>{label}</span></div>)}</div>
      </section>
      <section className="audit-results-grid">
        <article className="panel audit-results-panel">
          <div className="findings-heading"><div><h2>References</h2><p>Select a reference to review the details.</p></div><span>{results.length} shown</span></div>
          <label className="search-field compact findings-search"><Icon name="search" size={17} /><span className="sr-only">Search references</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search references…" /></label>
          <div className="reference-filter-bar">
            <button className={`all-references-filter${filter === "ALL" ? " active" : ""}`} type="button" aria-pressed={filter === "ALL"} onClick={() => setFilter("ALL")}><Icon name="library" size={14} /> All references <span>{audit.total_entries}</span></button>
            <div className="reference-status-group" role="group" aria-label="Filter by result status"><span className="reference-filter-label">Status</span><div className="filter-tabs findings-filters">{filterOptions.filter((option) => option.value !== "ALL").map((option) => <button type="button" aria-pressed={filter === option.value} className={filter === option.value ? "active" : ""} key={option.value} onClick={() => setFilter(option.value)}><i className={`filter-status-dot dot-${tone(option.value as AuditStatus)}`} />{option.label}<span>{audit.counts[option.value as AuditStatus] || 0}</span></button>)}</div></div>
          </div>
          <div className="finding-list">{results.map((result) => <button className={selected?.entry.entry_id === result.entry.entry_id ? "finding-card active" : "finding-card"} type="button" key={result.entry.entry_id} onClick={() => setSelectedId(result.entry.entry_id)}><span className={`risk-dot risk-${tone(result.status)}`} /><span className="finding-copy"><strong>{title(result)}</strong><small>{meta(result)}</small><em>{result.reason}</em></span><span className={`audit-status audit-status-${tone(result.status)}`}>{statusLabels[result.status]}</span></button>)}{results.length === 0 && <div className="table-empty">No references match this view.</div>}</div>
        </article>
        <aside className="panel audit-detail-panel">{selected ? <>
          <header><span className="eyebrow">Selected reference</span><h2>{title(selected)}</h2><span className={`audit-status audit-status-${tone(selected.status)}`}>{statusLabels[selected.status]}</span><p>{selected.reason}</p></header>
          <section><h3>Input metadata</h3><dl className="audit-metadata"><div><dt>Authors</dt><dd>{selected.entry.metadata.authors.join(", ") || "—"}</dd></div><div><dt>Year</dt><dd>{selected.entry.metadata.year || "—"}</dd></div><div><dt>Venue</dt><dd>{selected.entry.metadata.venue || "—"}</dd></div><div><dt>DOI</dt><dd>{selected.entry.metadata.doi || "—"}</dd></div><div><dt>Location</dt><dd>{selected.entry.page_start ? `Page ${selected.entry.page_start}${selected.entry.page_end && selected.entry.page_end !== selected.entry.page_start ? `–${selected.entry.page_end}` : ""}` : "—"}</dd></div></dl></section>
          {selected.matched_record && <section><h3>Matched publication</h3><strong>{selected.matched_record.metadata.title}</strong><p>{[selected.matched_record.metadata.authors.join(", "), selected.matched_record.metadata.venue, selected.matched_record.metadata.year].filter(Boolean).join(" · ")}</p><small>{selected.matched_record.provider} · {selected.matched_record.record_id}</small><a className="inline-link" href={selected.matched_record.url} target="_blank" rel="noreferrer">Open source record <Icon name="external" size={14} /></a></section>}
          {!selected.matched_record && <section><h3>Similar publications</h3><p>Possible matches for review. These records do not confirm the original citation.</p>{selected.candidates.length ? [...selected.candidates].sort((a, b) => titleOverlap(selected.entry.metadata.title, b.metadata.title) - titleOverlap(selected.entry.metadata.title, a.metadata.title)).map((candidate) => <a className="audit-candidate" href={candidate.url} target="_blank" rel="noreferrer" key={`${candidate.provider}-${candidate.record_id}`}><strong>{candidate.metadata.title}</strong><small>{candidate.metadata.authors.join(", ")} · {candidate.metadata.year || "Year unavailable"}</small><small>{candidate.provider} · {candidate.record_id}</small><small>{selected.entry.metadata.title ? `${Math.round(titleOverlap(selected.entry.metadata.title, candidate.metadata.title) * 100)}% title word overlap · not semantic similarity` : "Title similarity unavailable"}</small><span>Open candidate record ↗</span></a>) : <p>No similar publications were returned. Try checking the reference title or DOI.</p>}</section>}
          <section><h3>Field checks</h3>{selected.field_checks.length ? <div className="audit-field-list">{selected.field_checks.map((field) => <div key={field.field_name}><span className={`audit-field-status audit-field-${field.status.toLowerCase()}`}>{field.status.replace(/_/g, " ")}</span><strong>{field.field_name}</strong><p><span>Input: {field.input_value || "—"}</span><span>Source: {field.source_value || "—"}</span></p>{field.detail && <small>{field.detail}</small>}</div>)}</div> : <p>No field comparison was available for this result.</p>}</section>
          <section><h3>Lookup attempts</h3><div className="audit-attempts">{selected.lookup_attempts.map((attempt, index) => <div key={`${attempt.provider}-${index}`}><strong>{attempt.provider}</strong><span>{attempt.outcome.replace(/_/g, " ")}</span><p>{attempt.detail || attempt.error_code || "No additional detail."}</p></div>)}</div></section>
        </> : <div className="table-empty">Select a reference to inspect its details.</div>}</aside>
      </section>
    </>}
  </div>;
}
