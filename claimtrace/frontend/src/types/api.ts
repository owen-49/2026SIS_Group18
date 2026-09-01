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

export interface PaperRecord {
  paper_id: string;
  original_filename: string;
  file_type: "pdf" | "bib";
  file_size: number;
  status: ParseStatus;
  pages: number;
  paragraph_count: number;
  entry_count: number;
  title: string | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

export interface PaperListResponse {
  total: number;
  papers: PaperRecord[];
}

export type BibFieldStatus = "MATCH" | "MISMATCH" | "PDF_MISSING" | "BIB_MISSING" | "NOT_CHECKED";

export interface BibFieldResult {
  field_name: string;
  bib_value: string;
  pdf_value: string;
  status: BibFieldStatus;
  detail: string;
}

export interface BibEntryVerificationResult {
  citation_key: string;
  has_errors: boolean;
  error_count: number;
  warning_count: number;
  summary: string;
  fields: BibFieldResult[];
}

export interface BibVerifyResponse {
  bib_paper_id: string;
  total_entries: number;
  matched_entries: number;
  error_entries: number;
  results: BibEntryVerificationResult[];
}

export type CitationResolutionStatus = "identified" | "searching" | "not_found";

export interface IdentifiedSource {
  source_paper_id: string | null;
  citation_key: string;
  title: string;
  authors: string[];
  venue: string | null;
  year: number | null;
  doi: string | null;
  url: string | null;
  database: string | null;
}

export interface SimilarSource extends IdentifiedSource {
  similarity: number;
}

export interface SourceDocumentPage {
  page: number;
  heading: string | null;
  paragraphs: string[];
}

export interface SourceDocument {
  total_pages: number;
  pages: SourceDocumentPage[];
  matched_location: {
    page: number;
    paragraph_index: number;
  } | null;
}

export interface ExtractedClaim {
  claim_id: string;
  text: string;
  page: number | null;
  citation_marker: string;
  resolution_status: CitationResolutionStatus;
  cited_source: IdentifiedSource | null;
  similar_sources?: SimilarSource[];
  source_document?: SourceDocument | null;
  manuscript_location?: {
    page: number;
    paragraph_index: number;
  } | null;
}

export interface PaperClaimsResponse {
  manuscript_id: string;
  status: ParseStatus;
  claims: ExtractedClaim[];
  error_message: string | null;
  manuscript_document?: SourceDocument | null;
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
  source_location?: {
    page: number;
    quote: string;
    annotation?: string;
  };
  cited_source?: IdentifiedSource | null;
  source_passage?: string | null;
  source_document?: SourceDocument | null;
  comparison_rationale?: string | null;
  similar_sources?: SimilarSource[];
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
