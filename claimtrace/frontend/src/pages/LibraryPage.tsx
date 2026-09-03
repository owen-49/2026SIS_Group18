import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { getParseStatus, listPapers, usingMockApi } from "../api/client";
import { BibVerificationModal } from "../components/BibVerificationModal";
import { Icon } from "../components/Icon";
import { UploadPaperModal } from "../components/UploadPaperModal";
import type { PaperRecord, ParseStatus } from "../types/api";

const statusLabels: Record<ParseStatus, string> = {
  pending: "Pending",
  processing: "Processing",
  completed: "Completed",
  failed: "Failed",
};

function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function formatDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Unknown upload time";
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

function paperProgress(paper: PaperRecord) {
  if (paper.status === "failed") return "Processing failed";
  if (paper.status === "pending") return "Queued for processing";
  if (paper.status === "processing") return "Parsing in progress";
  if (paper.file_type === "bib") {
    return `${paper.entry_count} ${paper.entry_count === 1 ? "entry" : "entries"}`;
  }
  return `${paper.pages} ${paper.pages === 1 ? "page" : "pages"} · ${paper.paragraph_count} paragraphs`;
}

export function LibraryPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [query, setQuery] = useState("");
  const [papers, setPapers] = useState<PaperRecord[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusError, setStatusError] = useState<string | null>(null);
  const [uploadOpen, setUploadOpen] = useState(() => searchParams.get("upload") === "1");
  const [selectedBibId, setSelectedBibId] = useState<string | null>(null);

  const loadPapers = useCallback(async (signal?: AbortSignal, quiet = false) => {
    if (!quiet) setLoading(true);
    setError(null);
    try {
      const result = await listPapers(signal);
      if (signal?.aborted) return;
      setPapers(result.papers);
      setTotal(result.total);
    } catch (requestError) {
      if (signal?.aborted) return;
      setPapers([]);
      setTotal(0);
      setError(requestError instanceof Error ? requestError.message : "Unable to load the paper library.");
    } finally {
      if (!signal?.aborted && !quiet) setLoading(false);
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void loadPapers(controller.signal);
    return () => controller.abort();
  }, [loadPapers]);

  useEffect(() => {
    if (searchParams.get("upload") === "1") setUploadOpen(true);
  }, [searchParams]);

  const activePaperKey = useMemo(() => papers
    .filter((paper) => paper.status === "pending" || paper.status === "processing")
    .map((paper) => paper.paper_id)
    .sort()
    .join(","), [papers]);

  useEffect(() => {
    if (!activePaperKey) {
      setStatusError(null);
      return;
    }

    const controller = new AbortController();
    const paperIds = activePaperKey.split(",");
    let requestInFlight = false;

    const refreshStatuses = async () => {
      if (requestInFlight) return;
      requestInFlight = true;
      try {
        const statuses = await Promise.all(paperIds.map((paperId) => getParseStatus(paperId, controller.signal)));
        if (controller.signal.aborted) return;
        setStatusError(null);
        if (statuses.some((status) => status.status === "completed" || status.status === "failed")) {
          await loadPapers(controller.signal, true);
          return;
        }
        setPapers((current) => {
          let changed = false;
          const next = current.map((paper) => {
            const status = statuses.find((item) => item.paper_id === paper.paper_id);
            if (!status || (
              paper.status === status.status
              && paper.file_type === status.file_type
              && paper.pages === status.pages
              && paper.paragraph_count === status.paragraph_count
              && paper.entry_count === status.entry_count
              && (status.title === undefined || paper.title === status.title)
            )) return paper;
            changed = true;
            return {
              ...paper,
              status: status.status,
              file_type: status.file_type,
              pages: status.pages,
              paragraph_count: status.paragraph_count,
              entry_count: status.entry_count,
              title: status.title ?? paper.title,
            };
          });
          return changed ? next : current;
        });
      } catch (requestError) {
        if (!controller.signal.aborted) {
          setStatusError(requestError instanceof Error ? requestError.message : "Unable to refresh file processing status.");
        }
      } finally {
        requestInFlight = false;
      }
    };

    void refreshStatuses();
    const interval = window.setInterval(() => void refreshStatuses(), 2000);
    return () => {
      controller.abort();
      window.clearInterval(interval);
    };
  }, [activePaperKey, loadPapers]);

  const closeUpload = useCallback(() => {
    setUploadOpen(false);
    if (searchParams.has("upload")) {
      const next = new URLSearchParams(searchParams);
      next.delete("upload");
      setSearchParams(next, { replace: true });
    }
  }, [searchParams, setSearchParams]);

  const filteredPapers = useMemo(() => {
    const value = query.trim().toLowerCase();
    if (!value) return papers;
    return papers.filter((paper) =>
      [paper.title, paper.original_filename, paper.file_type, paper.status, paper.paper_id]
        .some((field) => field?.toLowerCase().includes(value)),
    );
  }, [papers, query]);

  const completedPdfPapers = useMemo(() => papers.filter((paper) =>
    paper.file_type === "pdf" && paper.status === "completed"), [papers]);
  const selectedBib = papers.find((paper) => paper.paper_id === selectedBibId && paper.file_type === "bib") || null;

  const resultLabel = query.trim()
    ? `${filteredPapers.length} of ${total}`
    : `${total} ${total === 1 ? "file" : "files"}`;

  return (
    <div className="page-stack">
      <section className="page-heading heading-row">
        <div><span className="eyebrow">Uploaded files</span><h1>Paper library</h1><p>Manage persisted PDF manuscripts and BibTeX bibliographies returned by the configured backend.</p></div>
        <button className="button button-primary" type="button" onClick={() => setUploadOpen(true)}><Icon name="upload" size={17} /> Upload files</button>
      </section>

      {usingMockApi && (
        <section className="library-mode-notice demo" role="status">
          <Icon name="spark" size={19} />
          <div><strong>Mock API active</strong><p>The files and metadata on this page are demo data, not real backend results.</p></div>
        </section>
      )}

      <section className="toolbar panel">
        <label className="search-field"><Icon name="search" size={18} /><span className="sr-only">Search files</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search title, file name, type, status, or ID…" disabled={loading || Boolean(error)} /></label>
        <span className="result-count" aria-live="polite">{loading ? "Loading…" : resultLabel}</span>
      </section>

      {statusError && <section className="library-status-error" role="alert"><Icon name="x" size={17} /><span><strong>Couldn’t refresh processing status.</strong> {statusError}</span></section>}

      {loading && (
        <section className="library-state panel" role="status">
          <span className="library-state-icon"><span className="spinner" /></span>
          <h2>Loading your file library</h2>
          <p>Reading persisted PDF and BibTeX metadata from ClaimTrace.</p>
        </section>
      )}

      {!loading && error && (
        <section className="library-state library-error panel" role="alert">
          <span className="library-state-icon"><Icon name="x" /></span>
          <h2>Couldn’t load the file library</h2>
          <p>{error}</p>
          <button className="button button-secondary" type="button" onClick={() => void loadPapers()}>Try again</button>
        </section>
      )}

      {!loading && !error && filteredPapers.length > 0 && (
        <section className="paper-grid">
          {filteredPapers.map((paper) => (
            <article className="paper-card" key={paper.paper_id}>
              <div className="paper-card-top">
                <span className={`paper-status status-${paper.status}`}><i />{statusLabels[paper.status]}</span>
                <span className={`file-type-badge file-type-${paper.file_type}`}>{paper.file_type}</span>
              </div>
              <h2>{paper.title || paper.original_filename}</h2>
              <p className="paper-file-name">{paper.original_filename}</p>
              <p>{formatBytes(paper.file_size)} · Uploaded {formatDate(paper.created_at)}</p>
              {paper.error_message && <p className="paper-error-message">{paper.error_message}</p>}
              {paper.file_type === "bib" && paper.status === "completed" && (
                <button className="button button-secondary paper-verify-bib" type="button" onClick={() => setSelectedBibId(paper.paper_id)}>
                  <Icon name="verify" size={15} /> Verify Bib metadata
                </button>
              )}
              <div className="paper-card-footer">
                <span><Icon name="document" size={16} /> {paperProgress(paper)}</span>
                <span className="paper-id" title={paper.paper_id}>ID {paper.paper_id.slice(0, 8)}</span>
              </div>
            </article>
          ))}
        </section>
      )}

      {!loading && !error && filteredPapers.length === 0 && (
        <section className="empty-state panel">
          <span className="empty-icon"><Icon name={query.trim() ? "search" : "library"} /></span>
          <h2>{query.trim() ? "No files found" : "Your file library is empty"}</h2>
          <p>{query.trim() ? "Try another title, file name, type, status, or ID." : "Upload a PDF or BibTeX file to add your first record."}</p>
          {query.trim()
            ? <button className="button button-secondary" type="button" onClick={() => setQuery("")}>Clear search</button>
            : <button className="button button-primary" type="button" onClick={() => setUploadOpen(true)}><Icon name="upload" size={17} /> Upload files</button>}
        </section>
      )}

      <UploadPaperModal open={uploadOpen} onClose={closeUpload} onUploaded={() => loadPapers(undefined, true)} />
      <BibVerificationModal bib={selectedBib} sourcePapers={completedPdfPapers} onClose={() => setSelectedBibId(null)} />
    </div>
  );
}
