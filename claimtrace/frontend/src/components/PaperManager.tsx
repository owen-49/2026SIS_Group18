import { useRef, useState } from "react";
import { deletePaper, usingMockApi } from "../api/client";
import type { PaperRecord } from "../types/api";
import { Icon } from "./Icon";
import { UploadFilesButton } from "./UploadFilesButton";
import type { ParsedPaper } from "../types/api";

interface Props {
  papers: PaperRecord[];
  selectedId: string;
  loading: boolean;
  busy: boolean;
  error: string | null;
  demo: boolean;
  onClose?: () => void;
  onRefresh: () => void;
  onSelect: (id: string) => void;
  onDeleted: (id: string) => void;
  onReady: (paper: ParsedPaper) => Promise<void>;
}
const statusLabels = { completed: "Ready", pending: "Pending", processing: "Processing", failed: "Failed" };

export function PaperManager({ papers, selectedId, loading, busy, error, demo, onRefresh, onSelect, onDeleted, onReady, onClose }: Props) {
  const [query, setQuery] = useState("");
  const [type, setType] = useState("all");
  const [target, setTarget] = useState<PaperRecord | null>(null);
  const [deleting, setDeleting] = useState(false);
  const deletingRef = useRef(false);
  const [deleteError, setDeleteError] = useState("");
  const [notice, setNotice] = useState("");
  const dialog = useRef<HTMLDialogElement>(null);
  const visible = papers.filter((paper) => (type === "all" || paper.file_type === type)
    && `${paper.original_filename} ${paper.title || ""}`.toLowerCase().includes(query.trim().toLowerCase()));

  async function confirmDelete() {
    if (!target || deletingRef.current) return;
    deletingRef.current = true;
    setDeleting(true); setDeleteError(""); setNotice("");
    try {
      await deletePaper(target.paper_id);
      onDeleted(target.paper_id);
      setNotice(`${target.original_filename} deleted.`);
      dialog.current?.close(); setTarget(null);
    } catch (cause) {
      setDeleteError(cause instanceof Error ? cause.message : "Unable to delete the paper.");
    } finally { deletingRef.current = false; setDeleting(false); }
  }

  return <section className="panel paper-manager" aria-labelledby="paper-manager-title">
    <header className="paper-manager-heading">
      <div className="paper-manager-title-group"><span className="paper-manager-title-icon"><Icon name="library" size={23} /></span><div><h2 id="paper-manager-title">Your papers <span>{papers.length}</span></h2><p>A home for your manuscripts and references.</p></div></div>
      <div className="paper-manager-actions"><button className="icon-button paper-refresh" aria-label="Refresh papers" title="Refresh papers" disabled={loading || deleting || busy} onClick={onRefresh} type="button">{loading ? <span className="spinner" /> : <Icon name="refresh" size={17} />}</button><UploadFilesButton disabled={busy || deleting} onReady={onReady} onSettled={onRefresh} />{onClose && <button className="icon-button paper-manager-close" type="button" aria-label="Close paper manager" disabled={deleting} onClick={onClose}><Icon name="x" size={19} /></button>}</div>
    </header>
    {demo && <p className="paper-manager-message">Example files are shown. Upload a file to manage your own papers.</p>}
    <div className="paper-manager-toolbar">
      <label className="search-field compact"><Icon name="search" size={17} /><span className="sr-only">Search papers</span><input placeholder="Search papers…" value={query} onChange={(event) => setQuery(event.target.value)} /></label>
      <div className="paper-type-tabs" role="group" aria-label="File type">{[{value: "all", label: "All files"}, {value: "pdf", label: "PDF"}, {value: "bib", label: "BibTeX"}].map((option) => <button type="button" key={option.value} aria-pressed={type === option.value} onClick={() => setType(option.value)}>{option.label}</button>)}</div>
    </div>
    {error && <p className="paper-manager-message paper-manager-error" role="alert">{error} Use Refresh to try again.</p>}
    {notice && <p className="paper-manager-message" role="status">{notice}</p>}
    {loading && <p className="paper-manager-message" role="status">Loading uploaded files…</p>}
    <ul className="paper-manager-list" aria-label="Uploaded papers">
      {visible.map((paper) => <li key={paper.paper_id} className={paper.paper_id === selectedId ? "is-selected" : ""}>
        <span className="paper-document-icon"><Icon name="document" size={21} /></span>
        <div className="paper-manager-name">
          <strong>{paper.original_filename}</strong>
          <div className="paper-manager-meta"><span>{paper.file_type === "bib" ? "BibTeX" : "PDF"}</span><span>{paper.file_size < 1024 * 1024 ? `${Math.ceil(paper.file_size / 1024)} KB` : `${(paper.file_size / 1024 / 1024).toFixed(1)} MB`}</span><span className={`paper-parse-status paper-parse-${paper.status}`}>{statusLabels[paper.status]}</span></div>
          {paper.error_message && <small className="paper-manager-error">{paper.error_message}</small>}
        </div>
        <div className="paper-row-actions"><button className="paper-select-button" type="button" aria-label={paper.paper_id === selectedId ? `${paper.original_filename} selected` : `Select ${paper.original_filename} for audit`} disabled={busy || deleting || loading || paper.status !== "completed" || paper.paper_id === selectedId} onClick={() => onSelect(paper.paper_id)}>{paper.paper_id === selectedId ? <><Icon name="check" size={14} /> Selected</> : "Select"}</button><button className="icon-button paper-delete-button" type="button" aria-label={`Delete ${paper.original_filename}`} title="Delete paper" disabled={busy || deleting || loading || (demo && !usingMockApi)} onClick={() => { setTarget(paper); setDeleteError(""); dialog.current?.showModal(); }}><Icon name="trash" size={17} /></button></div>
      </li>)}
    </ul>
    {!loading && !error && visible.length === 0 && <div className="table-empty"><strong>{papers.length ? "No matching papers" : "No papers uploaded yet"}</strong><p>{papers.length ? "Try another search or file type." : "Upload a PDF or BibTeX file to get started."}</p></div>}
    <dialog ref={dialog} className="direct-upload-dialog paper-delete-dialog" aria-labelledby="paper-delete-title" aria-describedby="paper-delete-description" onCancel={(event) => { if (deleting) event.preventDefault(); }}>
      <h2 id="paper-delete-title">Delete this paper?</h2><p className="paper-delete-filename">{target?.original_filename}</p><p id="paper-delete-description">This permanently removes the uploaded file and its generated data, including related audit results. This cannot be undone.</p>
      {deleteError && <p className="paper-manager-message paper-manager-error" role="alert">{deleteError} The paper has been kept in this list.</p>}
      <footer className="upload-dialog-footer"><button className="button button-secondary" type="button" autoFocus disabled={deleting} onClick={() => dialog.current?.close()}>Cancel</button><button className="button paper-delete-confirm" type="button" disabled={deleting} onClick={() => void confirmDelete()}>{deleting ? "Deleting…" : "Delete permanently"}</button></footer>
    </dialog>
  </section>;
}
