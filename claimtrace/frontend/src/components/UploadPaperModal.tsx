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
  state: "queued" | "uploading" | "complete" | "error";
  paperId?: string;
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
    const validFiles = Array.from(files).filter((file) => file.name.toLowerCase().endsWith(".pdf"));
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
        saveWorkspacePaper({ paperId: result.paper_id, fileName: item.file.name, uploadedAt: Date.now() });
        setItems((current) => current.map((entry) => entry.id === item.id
          ? { ...entry, state: "complete", paperId: result.paper_id }
          : entry));
        await onUploaded();
      } catch (error) {
        const message = error instanceof Error ? error.message : "Upload failed";
        setItems((current) => current.map((entry) => entry.id === item.id
          ? { ...entry, state: "error", error: message }
          : entry));
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
            <h2 id="library-upload-title">Upload manuscripts</h2>
            <p>Uploaded PDFs appear only in your Paper Library.</p>
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
          <input ref={inputRef} className="sr-only" type="file" accept=".pdf,application/pdf" multiple onChange={(event) => {
            if (event.target.files) void addFiles(event.target.files);
            event.target.value = "";
          }} />
          <span className="drop-icon"><Icon name="upload" size={24} /></span>
          <div><h3>Drop PDF manuscripts here</h3><p>PDF · up to 50 MB per file</p></div>
          <button className="button button-secondary" type="button" onClick={() => inputRef.current?.click()}>Choose files</button>
        </div>

        {items.length > 0 && (
          <div className="library-modal-queue">
            {items.map((item) => (
              <div className="upload-row" key={item.id}>
                <span className="file-icon"><Icon name="document" size={18} /></span>
                <div className="file-meta">
                  <strong>{item.file.name}</strong>
                  <p>{formatBytes(item.file.size)}{item.paperId ? ` · ID ${item.paperId}` : ""}</p>
                  {item.state === "uploading" && <span className="progress"><i /></span>}
                  {item.error && <small className="error-text">{item.error}</small>}
                </div>
                <span className={`upload-state state-${item.state}`}>
                  {item.state === "complete" && <Icon name="check" size={14} />}
                  {item.state === "queued" ? "Queued" : item.state === "uploading" ? "Uploading" : item.state === "complete" ? "Added" : "Failed"}
                </span>
                <button className="icon-button" type="button" aria-label={`Remove ${item.file.name}`} disabled={item.state === "uploading"} onClick={() => setItems((current) => current.filter((entry) => entry.id !== item.id))}><Icon name="x" size={16} /></button>
              </div>
            ))}
          </div>
        )}

        <footer className="library-upload-footer">
          <span><Icon name="shield" size={16} /> Academic database matches are kept outside this library.</span>
          <button className="button button-primary" type="button" disabled={uploading} onClick={onClose}>{uploading ? "Uploading…" : "Done"}</button>
        </footer>
      </section>
    </div>
  );
}
