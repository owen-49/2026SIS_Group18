import { demoAudit, demoVerification } from "../data/mockData";
import type { AuditResponse, ParsedPaper, VerifyResponse } from "../types/api";

const API_BASE = (import.meta.env.VITE_API_URL || "").replace(/\/$/, "");
export const usingMockApi = import.meta.env.VITE_USE_MOCK_API !== "false";

function apiUrl(path: string) {
  return `${API_BASE}${path}`;
}

async function readResponse<T>(response: Response): Promise<T> {
  if (response.ok) return response.json() as Promise<T>;

  let message = `Request failed (${response.status})`;
  try {
    const body = (await response.json()) as { detail?: string };
    if (body.detail) message = body.detail;
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
