export interface WorkspacePaper {
  paperId: string;
  fileName: string;
  uploadedAt: number;
}

const STORAGE_KEY = "claimtrace.workspacePapers";
const DEMO_PAPER: WorkspacePaper = {
  paperId: "paper-manuscript",
  fileName: "transformer-literature-review.pdf",
  uploadedAt: 0,
};

export function getWorkspacePapers(): WorkspacePaper[] {
  try {
    const stored = window.sessionStorage.getItem(STORAGE_KEY);
    const papers = stored ? JSON.parse(stored) as WorkspacePaper[] : [];
    return papers.length ? papers : [DEMO_PAPER];
  } catch {
    return [DEMO_PAPER];
  }
}

export function saveWorkspacePaper(paper: WorkspacePaper) {
  const current = getWorkspacePapers().filter((entry) => entry.paperId !== DEMO_PAPER.paperId && entry.paperId !== paper.paperId);
  window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify([paper, ...current].slice(0, 20)));
}
