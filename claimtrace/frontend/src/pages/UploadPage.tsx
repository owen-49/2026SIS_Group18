import { useState } from "react";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

interface ParseResult {
  paper_id: string;
  status: string;
  pages: number;
  paragraph_count: number;
}

export function UploadPage() {
  const [uploading, setUploading] = useState(false);
  const [results, setResults] = useState<ParseResult[]>([]);
  const [error, setError] = useState<string | null>(null);

  async function handleUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const files = e.target.files;
    if (!files) return;

    setUploading(true);
    setError(null);

    for (const file of Array.from(files)) {
      try {
        const formData = new FormData();
        formData.append("file", file);

        const resp = await fetch(`${API_BASE}/api/parse`, {
          method: "POST",
          body: formData,
        });

        if (!resp.ok) throw new Error(`Upload failed: ${resp.statusText}`);

        const data: ParseResult = await resp.json();
        setResults((prev) => [...prev, data]);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Upload failed");
      }
    }

    setUploading(false);
  }

  return (
    <div className="page">
      <h2>Upload Papers</h2>
      <p>Upload your manuscript and all cited source PDFs to begin the audit.</p>

      <div className="upload-zone">
        <input
          type="file"
          accept=".pdf"
          multiple
          onChange={handleUpload}
          disabled={uploading}
        />
        {uploading && <p>Uploading and parsing...</p>}
      </div>

      {error && <div className="error">{error}</div>}

      {results.length > 0 && (
        <div className="results">
          <h3>Uploaded Papers</h3>
          <table>
            <thead>
              <tr>
                <th>Paper ID</th>
                <th>Status</th>
                <th>Pages</th>
                <th>Paragraphs</th>
              </tr>
            </thead>
            <tbody>
              {results.map((r) => (
                <tr key={r.paper_id}>
                  <td>{r.paper_id}</td>
                  <td>{r.status}</td>
                  <td>{r.pages}</td>
                  <td>{r.paragraph_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
