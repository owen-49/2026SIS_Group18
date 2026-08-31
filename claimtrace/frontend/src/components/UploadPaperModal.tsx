import { useEffect, useRef, useState } from "react";
import { uploadPaper } from "../api/client";
import { saveWorkspacePaper } from "../data/workspacePapers";
import { Icon } from "./Icon";

interface UploadPaperModalProps {
  open: boolean;
  onClose: () => void;
  onUploaded: () => void | Promise<void>;
}

interface UploadItem {
  id: string;
  file: File;
  state: "queued" | "uploading" | "processing" | "complete" | "error";
  paperId?: string;
  summary?: string;
  error?: string;
}

function formatBytes(bytes: number) {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export function UploadPaperModal({ open, onClose, onUploaded }: UploadPaperModalProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [items, setItems] = useState<UploadItem[]>([]);
  const [dragging, setDragging] = useState(false);
  const [selectionError, setSelectionError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !items.some((item) => item.state === "uploading")) onClose();
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [items, onClose, open]);

  if (!open) return null;

  async function addFiles(files: FileList | File[]) {
    const selectedFiles = Array.from(files);
    const validFiles = selectedFiles.filter((file) => /\.(pdf|bib)$/i.test(file.name));
    const invalidCount = selectedFiles.length - validFiles.length;
    setSelectionError(invalidCount > 0
      ? `${invalidCount} ${invalidCount === 1 ? "file was" : "files were"} skipped. Only PDF and .bib files are supported.`
      : null);
    if (!validFiles.length) return;

    const nextItems = validFiles.map((file) => ({
      id: crypto.randomUUID(),
      file,
      state: "queued" as const,
    }));
    setItems((current) => [...nextItems, ...current]);

    for (const item of nextItems) {
      setItems((current) => current.map((entry) => entry.id === item.id ? { ...entry, state: "uploading" } : entry));
      try {
        const result = await uploadPaper(item.file);
        saveWorkspacePaper({
          paperId: result.paper_id,
          fileName: item.file.name,
          uploadedAt: Date.now(),
          fileType: result.file_type,
          fileSize: item.file.size,
          status: result.status,
          pages: result.pages,
          paragraphCount: result.paragraph_count,
          entryCount: result.entry_count,
        });
        const summary = result.file_type === "bib"
          ? `${result.entry_count} ${result.entry_count === 1 ? "entry" : "entries"}`
          : `${result.pages} ${result.pages === 1 ? "page" : "pages"} · ${result.paragraph_count} paragraphs`;
        setItems((current) => current.map((entry) => entry.id === item.id
          ? {
              ...entry,
              state: result.status === "completed" ? "complete" : result.status === "failed" ? "error" : "processing",
              paperId: result.paper_id,
              summary,
              error: result.status === "failed" ? "The backend could not process this file." : undefined,
            }
          : entry));
        await onUploaded();
      } catch (error) {
        const message = error instanceof Error ? error.message : "Upload failed";
        setItems((current) => current.map((entry) => entry.id === item.id
          ? { ...entry, state: "error", error: message }
          : entry));
        await onUploaded();
      }
    }
  }

  const uploading = items.some((item) => item.state === "uploading");

  return (
    <div className="library-upload-overlay" role="presentation" onMouseDown={(event) => {
      if (event.currentTarget === event.target && !uploading) onClose();
    }}>
      <section className="library-upload-modal" role="dialog" aria-modal="true" aria-labelledby="library-upload-title">
        <header className="library-upload-heading">
          <div>
            <span className="eyebrow">Paper library</span>
            <h2 id="library-upload-title">Upload files</h2>
            <p>Upload PDF manuscripts and BibTeX bibliographies to your Library.</p>
          </div>
          <button className="icon-button" type="button" aria-label="Close upload window" disabled={uploading} onClick={onClose}><Icon name="x" /></button>
        </header>

        <div
          className={dragging ? "library-modal-drop dragging" : "library-modal-drop"}
          onDragEnter={(event) => { event.preventDefault(); setDragging(true); }}
          onDragOver={(event) => event.preventDefault()}
          onDragLeave={(event) => { if (event.currentTarget === event.target) setDragging(false); }}
          onDrop={(event) => {
            event.preventDefault();
            setDragging(false);
            void addFiles(event.dataTransfer.files);
          }}
        >
          <input ref={inputRef} className="sr-only" type="file" accept=".pdf,.bib,application/pdf,application/x-bibtex,text/x-bibtex" multiple onChange={(event) => {
            if (event.target.files) void addFiles(event.target.files);
            event.target.value = "";
          }} />
          <span className="drop-icon"><Icon name="upload" size={24} /></span>
          <div><h3>Drop PDF or BibTeX files here</h3><p>PDF or .bib · backend size limits apply</p></div>
          <button className="button button-secondary" type="button" onClick={() => inputRef.current?.click()}>Choose files</button>
        </div>

        {selectionError && <p className="library-upload-selection-error" role="alert">{selectionError}</p>}

        {items.length > 0 && (
          <div className="library-modal-queue">
            {items.map((item) => (
              <div className="upload-row" key={item.id}>
                <span className={item.file.name.toLowerCase().endsWith(".bib") ? "file-icon bib" : "file-icon"}><Icon name="document" size={18} /></span>
                <div className="file-meta">
                  <strong>{item.file.name}</strong>
                  <p>{formatBytes(item.file.size)}{item.summary ? ` · ${item.summary}` : ""}{item.paperId ? ` · ID ${item.paperId}` : ""}</p>
                  {(item.state === "uploading" || item.state === "processing") && <span className="progress"><i /></span>}
                  {item.error && <small className="error-text">{item.error}</small>}
                </div>
                <span className={`upload-state state-${item.state}`}>
                  {item.state === "complete" && <Icon name="check" size={14} />}
                  {item.state === "queued" ? "Queued" : item.state === "uploading" ? "Uploading" : item.state === "processing" ? "Processing" : item.state === "complete" ? "Added" : "Failed"}
                </span>
                <button className="icon-button" type="button" aria-label={`Remove ${item.file.name}`} disabled={item.state === "uploading"} onClick={() => setItems((current) => current.filter((entry) => entry.id !== item.id))}><Icon name="x" size={16} /></button>
              </div>
            ))}
          </div>
        )}

        <footer className="library-upload-footer">
          <span><Icon name="shield" size={16} /> Files are parsed and persisted by the configured backend.</span>
          <button className="button button-primary" type="button" disabled={uploading} onClick={onClose}>{uploading ? "Uploading…" : "Done"}</button>
        </footer>
      </section>
    </div>
  );
}
