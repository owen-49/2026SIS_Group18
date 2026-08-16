import { useRef, useState } from "react";
import { uploadPaper } from "../api/client";
import { Icon } from "../components/Icon";
import type { ParsedPaper } from "../types/api";

interface UploadItem {
  id: string;
  file: File;
  state: "queued" | "uploading" | "complete" | "error";
  result?: ParsedPaper;
  error?: string;
}

function formatBytes(bytes: number) {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export function UploadPage() {
  const inputRef = useRef<HTMLInputElement>(null);
  const [items, setItems] = useState<UploadItem[]>([]);
  const [dragging, setDragging] = useState(false);

  async function addFiles(files: FileList | File[]) {
    const validFiles = Array.from(files).filter((file) => /\.(pdf|bib)$/i.test(file.name));
    const nextItems = validFiles.map((file) => ({ id: crypto.randomUUID(), file, state: "queued" as const }));
    setItems((current) => [...nextItems, ...current]);

    for (const item of nextItems) {
      setItems((current) => current.map((entry) => entry.id === item.id ? { ...entry, state: "uploading" } : entry));
      try {
        const result = await uploadPaper(item.file);
        setItems((current) => current.map((entry) => entry.id === item.id ? { ...entry, state: "complete", result } : entry));
      } catch (error) {
        const message = error instanceof Error ? error.message : "Upload failed";
        setItems((current) => current.map((entry) => entry.id === item.id ? { ...entry, state: "error", error: message } : entry));
      }
    }
  }

  return (
    <div className="page-stack narrow-page">
      <section className="page-heading"><span className="eyebrow">Build your evidence base</span><h1>Upload papers</h1><p>Add a manuscript, source PDFs, or a BibTeX file. ClaimTrace keeps each source local while it prepares the evidence index.</p></section>

      <section
        className={dragging ? "drop-zone dragging" : "drop-zone"}
        onDragEnter={(event) => { event.preventDefault(); setDragging(true); }}
        onDragOver={(event) => event.preventDefault()}
        onDragLeave={(event) => { if (event.currentTarget === event.target) setDragging(false); }}
        onDrop={(event) => { event.preventDefault(); setDragging(false); void addFiles(event.dataTransfer.files); }}
      >
        <input ref={inputRef} className="sr-only" type="file" accept=".pdf,.bib" multiple onChange={(event) => event.target.files && void addFiles(event.target.files)} />
        <span className="drop-icon"><Icon name="upload" size={27} /></span>
        <h2>Drop papers here</h2>
        <p>PDF or BibTeX · up to 50 MB per file</p>
        <button className="button button-secondary" type="button" onClick={() => inputRef.current?.click()}>Choose files</button>
      </section>

      <section className="privacy-note"><Icon name="shield" size={18} /><div><strong>Local-first by design</strong><p>Your source files stay in this workspace. Only the claim and matched passage are sent for verification.</p></div></section>

      {items.length > 0 && (
        <section className="panel upload-list">
          <div className="panel-heading"><div><h2>Upload queue</h2><p>{items.filter((item) => item.state === "complete").length} of {items.length} ready</p></div><button className="text-button" type="button" onClick={() => setItems([])}>Clear all</button></div>
          {items.map((item) => (
            <div className="upload-row" key={item.id}>
              <span className={`file-icon ${item.file.name.endsWith(".bib") ? "bib" : "pdf"}`}><Icon name="document" size={19} /></span>
              <div className="file-meta"><strong>{item.file.name}</strong><p>{formatBytes(item.file.size)}{item.result?.paper_id && ` · ID ${item.result.paper_id}`}</p>{item.state === "uploading" && <span className="progress"><i /></span>}{item.error && <small className="error-text">{item.error}</small>}</div>
              <span className={`upload-state state-${item.state}`}>{item.state === "complete" && <Icon name="check" size={15} />}{item.state === "queued" ? "Queued" : item.state === "uploading" ? "Processing" : item.state === "complete" ? "Ready" : "Failed"}</span>
              <button className="icon-button" aria-label={`Remove ${item.file.name}`} onClick={() => setItems((current) => current.filter((entry) => entry.id !== item.id))}><Icon name="x" size={17} /></button>
            </div>
          ))}
        </section>
      )}
    </div>
  );
}
