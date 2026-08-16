export type Verdict = "SUPPORT" | "PARTIAL" | "CONTRADICT" | "NOT_FOUND";
export type ParseStatus = "pending" | "processing" | "completed" | "failed";

export interface ParsedPaper {
  paper_id: string;
  status: ParseStatus;
  file_type: "pdf" | "bib";
  pages: number;
  paragraph_count: number;
  entry_count: number;
  title?: string;
  file_name?: string;
}

export interface LibraryPaper {
  id: string;
  citationKey: string;
  title: string;
  authors: string;
  venue: string;
  year: number;
  url?: string;
  status: "linked" | "missing" | "review";
}

export interface MatchResult {
  passage_text: string;
  similarity: number;
  entailment_label: Verdict;
  confidence: number;
}

export interface VerifyResponse {
  claim: string;
  verdict: Verdict;
  confidence: number;
  rationale: string;
  matches: MatchResult[];
}

export interface CitationAuditResult {
  citation_key: string;
  claim: string;
  verdict: Verdict;
  confidence: number;
  risk_level: "high" | "medium" | "low";
}

export interface AuditResponse {
  manuscript_id: string;
  total_citations: number;
  supported: number;
  partial: number;
  contradicted: number;
  not_found: number;
  results: CitationAuditResult[];
}
