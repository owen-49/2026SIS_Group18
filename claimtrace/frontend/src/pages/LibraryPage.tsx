import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { listPapers } from "../api/client";
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
  if (paper.file_type === "bib") {
    return paper.entry_count > 0
      ? `${paper.entry_count} ${paper.entry_count === 1 ? "entry" : "entries"}`
      : "Waiting for parsing";
  }
  if (paper.pages > 0 || paper.paragraph_count > 0) {
    return `${paper.pages} ${paper.pages === 1 ? "page" : "pages"} · ${paper.paragraph_count} paragraphs`;
  }
  return "Waiting for parsing";
}

export function LibraryPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [query, setQuery] = useState("");
  const [papers, setPapers] = useState<PaperRecord[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [uploadOpen, setUploadOpen] = useState(() => searchParams.get("upload") === "1");

  const loadPapers = useCallback(async (signal?: AbortSignal) => {
    setLoading(true);
    setError(null);
    try {
      const result = await listPapers(signal);
      if (signal?.aborted) return;
      const uploadedPdfs = result.papers.filter((paper) => paper.file_type === "pdf");
      setPapers(uploadedPdfs);
      setTotal(uploadedPdfs.length);
    } catch (requestError) {
      if (signal?.aborted) return;
      setPapers([]);
      setTotal(0);
      setError(requestError instanceof Error ? requestError.message : "Unable to load the paper library.");
    } finally {
      if (!signal?.aborted) setLoading(false);
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

  const resultLabel = query.trim()
    ? `${filteredPapers.length} of ${total}`
    : `${total} ${total === 1 ? "paper" : "papers"}`;

  return (
    <div className="page-stack">
      <section className="page-heading heading-row">
        <div><span className="eyebrow">Uploaded manuscripts</span><h1>Paper library</h1><p>Only papers you upload appear here. Database-identified citation sources stay in the review results.</p></div>
        <button className="button button-primary" type="button" onClick={() => setUploadOpen(true)}><Icon name="upload" size={17} /> Upload papers</button>
      </section>

      <section className="toolbar panel">
        <label className="search-field"><Icon name="search" size={18} /><span className="sr-only">Search papers</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search title, file name, status, or paper ID…" disabled={loading || Boolean(error)} /></label>
        <span className="result-count" aria-live="polite">{loading ? "Loading…" : resultLabel}</span>
      </section>

      {loading && (
        <section className="library-state panel" role="status">
          <span className="library-state-icon"><span className="spinner" /></span>
          <h2>Loading your paper library</h2>
          <p>Reading your uploaded manuscript metadata from ClaimTrace.</p>
        </section>
      )}

      {!loading && error && (
        <section className="library-state library-error panel" role="alert">
          <span className="library-state-icon"><Icon name="x" /></span>
          <h2>Couldn’t load the paper library</h2>
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
          <h2>{query.trim() ? "No papers found" : "Your paper library is empty"}</h2>
          <p>{query.trim() ? "Try another title, file name, status, or paper ID." : "Upload a PDF or BibTeX file to add your first source."}</p>
          {query.trim()
            ? <button className="button button-secondary" type="button" onClick={() => setQuery("")}>Clear search</button>
            : <button className="button button-primary" type="button" onClick={() => setUploadOpen(true)}><Icon name="upload" size={17} /> Upload papers</button>}
        </section>
      )}

      <UploadPaperModal open={uploadOpen} onClose={closeUpload} onUploaded={() => loadPapers()} />
    </div>
  );
}
