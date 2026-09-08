import { useEffect, useRef, useState } from "react";
import { getParseStatus, uploadPaper, usingMockApi } from "../api/client";
import { saveWorkspacePaper } from "../data/workspacePapers";
import type { ParsedPaper } from "../types/api";
import { Icon } from "./Icon";

interface Props {
  pdfOnly?: boolean;
  onReady: (paper: ParsedPaper) => Promise<void>;
}

export function UploadFilesButton({ pdfOnly = false, onReady }: Props) {
  const dialog = useRef<HTMLDialogElement>(null);
  const active = useRef(true);
  const busyRef = useRef(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [dragging, setDragging] = useState(false);
  useEffect(() => {
    active.current = true;
    return () => { active.current = false; };
  }, []);

  async function upload(file: File) {
    if (busyRef.current) return;
    setError("");
    if (!(pdfOnly ? /\.pdf$/i : /\.(pdf|bib)$/i).test(file.name)) {
      setError(pdfOnly ? "Choose a PDF file." : "Choose a PDF or .bib file.");
      return;
    }
    busyRef.current = true;
    setBusy(true);
    setMessage(`Uploading ${file.name}…`);
    try {
      let paper = await uploadPaper(file);
      // Mock status polling reads the local workspace record.
      saveWorkspacePaper({ paperId: paper.paper_id, fileName: file.name, fileType: paper.file_type,
        fileSize: file.size, uploadedAt: Date.now(), status: paper.status, pages: paper.pages,
        paragraphCount: paper.paragraph_count, entryCount: paper.entry_count });
      while (active.current && (paper.status === "pending" || paper.status === "processing")) {
        setMessage(`${file.name} uploaded. Parsing…`);
        await new Promise((resolve) => window.setTimeout(resolve, 2000));
        if (!active.current) return;
        paper = await getParseStatus(paper.paper_id);
      }
      if (!active.current) return;
      if (paper.status === "failed") throw new Error("Parsing failed. Please check the file and try again.");
      setMessage(`${file.name} is ready. Refreshing the file list…`);
      await onReady(paper);
      if (active.current) setMessage(`${file.name} is ready and selected. You can close this window or upload another file.`);
    } catch (cause) {
      if (active.current) { setMessage(""); setError(cause instanceof Error ? cause.message : "Upload failed. Please try again."); }
    } finally {
      busyRef.current = false;
      if (active.current) setBusy(false);
    }
  }

  return <>
    <button className="button button-secondary upload-trigger" type="button" onClick={() => dialog.current?.showModal()}><Icon name="upload" size={17} /> Upload {pdfOnly ? "PDF" : "file"}</button>
    <dialog className="direct-upload-dialog" aria-labelledby="direct-upload-title" ref={dialog} onCancel={(event) => { if (busy) event.preventDefault(); }}>
      <header><div className="upload-heading"><span className="upload-heading-icon"><Icon name="upload" size={24} /></span><div><h2 id="direct-upload-title">Upload {pdfOnly ? "PDF" : "file"}</h2></div></div><button className="icon-button" type="button" aria-label="Close upload window" disabled={busy} onClick={() => dialog.current?.close()}><Icon name="x" /></button></header>
      <p className="upload-description">{pdfOnly ? "Add a manuscript or source paper to start reviewing its claims." : "Add a manuscript or bibliography to check your references."}</p>
      {usingMockApi && <p>Demo mode: files are simulated and are not saved to the backend.</p>}
      <label className={`direct-upload-input${dragging ? " is-dragging" : ""}${busy ? " is-busy" : ""}`} onDragOver={(event) => { event.preventDefault(); if (!busy) setDragging(true); }} onDragLeave={() => setDragging(false)} onDrop={(event) => {
        event.preventDefault(); setDragging(false);
        if (!busy && event.dataTransfer.files[0]) void upload(event.dataTransfer.files[0]);
      }}>
        <span className="upload-drop-icon"><Icon name="document" size={30} /></span>
        <strong>{busy ? "Preparing your file…" : "Drop your file here"}</strong>
        <span className="upload-browse">or <span>browse files</span> on your computer</span>
        <span className="upload-formats"><span>PDF</span>{!pdfOnly && <span>BibTeX</span>}<small>One file at a time</small></span>
        <input aria-label={pdfOnly ? "Choose a PDF" : "Choose a PDF or BibTeX file"} type="file" accept={pdfOnly ? ".pdf,application/pdf" : ".pdf,.bib,application/pdf"} disabled={busy} onChange={(event) => {
        const file = event.target.files?.[0];
        event.target.value = "";
        if (file) void upload(file);
      }} /></label>
      {message && <p className="upload-feedback" role="status">{busy ? <span className="spinner" /> : <Icon name="check" size={18} />} <span>{message}</span></p>}
      {error && <p className="upload-feedback upload-feedback-error" role="alert"><Icon name="x" size={18} /><span>{error}</span></p>}
      <footer className="upload-dialog-footer"><span><Icon name="document" size={16} /> Ready files are selected automatically</span><button className="button button-primary" type="button" disabled={busy} onClick={() => dialog.current?.close()}>{busy ? "Processing…" : "Done"}</button></footer>
    </dialog>
  </>;
}
