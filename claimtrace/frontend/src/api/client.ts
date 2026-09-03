import { demoAudit, demoPaperClaims, demoVerification } from "../data/mockData";
import { getWorkspacePapers } from "../data/workspacePapers";
import type { AuditResponse, BibVerifyResponse, PaperClaimsResponse, PaperListResponse, ParsedPaper, VerifyResponse } from "../types/api";

const API_BASE = (import.meta.env.VITE_API_URL || "http://localhost:8000").replace(/\/$/, "");
export const usingMockApi = import.meta.env.VITE_USE_MOCK_API === "true";

function apiUrl(path: string) {
  return `${API_BASE}${path}`;
}

async function readResponse<T>(response: Response): Promise<T> {
  if (response.ok) return response.json() as Promise<T>;

  let message = `Request failed (${response.status})`;
  try {
    const body = (await response.json()) as { detail?: string | Array<{ msg?: string }> };
    if (typeof body.detail === "string") message = body.detail;
    if (Array.isArray(body.detail)) {
      const details = body.detail.map((item) => item.msg).filter(Boolean).join("; ");
      if (details) message = details;
    }
  } catch {
    // Keep the status-based fallback when the server does not return JSON.
  }
  throw new Error(message);
}

function wait(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

export async function uploadPaper(file: File): Promise<ParsedPaper> {
  if (usingMockApi) {
    await wait(700);
    const fileType = file.name.toLowerCase().endsWith(".bib") ? "bib" : "pdf";
    return {
      paper_id: crypto.randomUUID().slice(0, 8),
      status: "completed",
      file_type: fileType,
      pages: fileType === "pdf" ? Math.max(4, Math.round(file.size / 45_000)) : 0,
      paragraph_count: fileType === "pdf" ? Math.max(24, Math.round(file.size / 4_000)) : 0,
      entry_count: fileType === "bib" ? 4 : 0,
      title: file.name.replace(/\.(pdf|bib)$/i, ""),
      file_name: file.name,
    };
  }

  const formData = new FormData();
  formData.append("file", file);
  const response = await fetch(apiUrl("/api/parse"), { method: "POST", body: formData });
  return { ...(await readResponse<ParsedPaper>(response)), file_name: file.name };
}

export async function listPapers(signal?: AbortSignal): Promise<PaperListResponse> {
  if (usingMockApi) {
    await wait(350);
    const papers = getWorkspacePapers().map((paper, index) => ({
      paper_id: paper.paperId,
      original_filename: paper.fileName,
      file_type: paper.fileType || "pdf",
      file_size: paper.fileSize ?? 1_640_000 + index * 120_000,
      status: paper.status || "completed",
      pages: paper.pages ?? (paper.fileType === "bib" ? 0 : 12 + index * 2),
      paragraph_count: paper.paragraphCount ?? (paper.fileType === "bib" ? 0 : 146 + index * 18),
      entry_count: paper.entryCount ?? 0,
      title: paper.fileName.replace(/\.(pdf|bib)$/i, "").replace(/[-_]+/g, " "),
      error_message: null,
      created_at: paper.uploadedAt
        ? new Date(paper.uploadedAt).toISOString()
        : new Date(Date.UTC(2026, 7, 16, 4, 30)).toISOString(),
      updated_at: paper.uploadedAt
        ? new Date(paper.uploadedAt).toISOString()
        : new Date(Date.UTC(2026, 7, 16, 4, 30)).toISOString(),
    }));
    return { total: papers.length, papers };
  }

  const response = await fetch(apiUrl("/api/papers"), { signal });
  const result = await readResponse<PaperListResponse>(response);
  if (!Array.isArray(result.papers)) throw new Error("The paper library response is invalid.");
  return result;
}

export async function getParseStatus(paperId: string, signal?: AbortSignal): Promise<ParsedPaper> {
  if (usingMockApi) {
    await wait(200);
    const paper = getWorkspacePapers().find((entry) => entry.paperId === paperId);
    if (!paper) throw new Error("File not found in the demo workspace.");
    return {
      paper_id: paper.paperId,
      status: paper.status || "completed",
      file_type: paper.fileType || "pdf",
      pages: paper.pages || 0,
      paragraph_count: paper.paragraphCount || 0,
      entry_count: paper.entryCount || 0,
      title: paper.fileName.replace(/\.(pdf|bib)$/i, ""),
      file_name: paper.fileName,
    };
  }

  const response = await fetch(apiUrl(`/api/parse/${encodeURIComponent(paperId)}`), { signal });
  return readResponse<ParsedPaper>(response);
}

export async function verifyBib(
  bibPaperId: string,
  sourcePaperIds: string[],
  signal?: AbortSignal,
): Promise<BibVerifyResponse> {
  if (usingMockApi) {
    await wait(650);
    return {
      bib_paper_id: bibPaperId,
      total_entries: 1,
      matched_entries: 0,
      error_entries: 0,
      results: [{
        citation_key: "demo-entry",
        has_errors: false,
        error_count: 0,
        warning_count: 1,
        summary: "Demo preview: PDF metadata is not available for comparison.",
        fields: [{
          field_name: "title",
          bib_value: "Example bibliography title",
          pdf_value: "",
          status: "PDF_MISSING",
          detail: "Demo result only — connect the FastAPI backend for real metadata verification.",
        }],
      }],
    };
  }

  const response = await fetch(apiUrl("/api/verify/bib"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ bib_paper_id: bibPaperId, source_paper_ids: sourcePaperIds }),
    signal,
  });
  return readResponse<BibVerifyResponse>(response);
}

export async function getPaperClaims(paperId: string, signal?: AbortSignal): Promise<PaperClaimsResponse> {
  if (usingMockApi) {
    await wait(600);
    return { ...demoPaperClaims, manuscript_id: paperId };
  }

  const response = await fetch(apiUrl(`/api/papers/${encodeURIComponent(paperId)}/claims`), { signal });
  const result = await readResponse<PaperClaimsResponse>(response);
  if (!Array.isArray(result.claims)) throw new Error("The extracted claims response is invalid.");
  return result;
}

export async function verifyClaim(claim: string, sourcePaperId: string): Promise<VerifyResponse> {
  if (usingMockApi) {
    await wait(900);
    return { ...demoVerification, claim };
  }

  const response = await fetch(apiUrl("/api/verify"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ claim, source_paper_id: sourcePaperId }),
  });
  return readResponse<VerifyResponse>(response);
}

export async function runAudit(
  manuscriptId: string,
  sourcePaperIds: string[],
): Promise<AuditResponse> {
  if (usingMockApi) {
    await wait(1100);
    return { ...demoAudit, manuscript_id: manuscriptId };
  }

  const response = await fetch(apiUrl("/api/audit"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ manuscript_id: manuscriptId, source_paper_ids: sourcePaperIds }),
  });
  return readResponse<AuditResponse>(response);
}
