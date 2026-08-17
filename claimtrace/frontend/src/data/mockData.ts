import type { AuditResponse, LibraryPaper, VerifyResponse } from "../types/api";

export const libraryPapers: LibraryPaper[] = [
  {
    id: "paper-attention",
    citationKey: "vaswani2017attention",
    title: "Attention Is All You Need",
    authors: "Vaswani et al.",
    venue: "NeurIPS",
    year: 2017,
    url: "https://arxiv.org/abs/1706.03762",
    status: "linked",
  },
  {
    id: "paper-bert",
    citationKey: "devlin2019bert",
    title: "BERT: Pre-training of Deep Bidirectional Transformers",
    authors: "Devlin et al.",
    venue: "NAACL",
    year: 2019,
    url: "https://aclanthology.org/N19-1423",
    status: "linked",
  },
  {
    id: "paper-gpt3",
    citationKey: "brown2020language",
    title: "Language Models are Few-Shot Learners",
    authors: "Brown et al.",
    venue: "NeurIPS",
    year: 2020,
    url: "https://arxiv.org/abs/2005.14165",
    status: "linked",
  },
  {
    id: "paper-rag",
    citationKey: "lewis2020retrieval",
    title: "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks",
    authors: "Lewis et al.",
    venue: "NeurIPS",
    year: 2020,
    url: "https://arxiv.org/abs/2005.11401",
    status: "review",
  },
];

export const demoVerification: VerifyResponse = {
  claim:
    "Self-attention enables the model to relate information from different positions in a sequence without recurrence.",
  verdict: "SUPPORT",
  confidence: 0.94,
  rationale:
    "The source directly describes the Transformer as relying entirely on attention mechanisms and dispensing with recurrence and convolutions.",
  matches: [
    {
      passage_text:
        "We propose a new simple network architecture, the Transformer, based solely on attention mechanisms, dispensing with recurrence and convolutions entirely.",
      similarity: 0.91,
      entailment_label: "SUPPORT",
      confidence: 0.94,
    },
  ],
};

export const demoAudit: AuditResponse = {
  manuscript_id: "transformer-survey.pdf",
  total_citations: 12,
  supported: 8,
  partial: 2,
  contradicted: 1,
  not_found: 1,
  results: [
    {
      citation_key: "vaswani2017attention",
      claim: "The Transformer removes recurrence in favour of attention mechanisms.",
      verdict: "SUPPORT",
      confidence: 0.94,
      risk_level: "low",
      source_location: {
        page: 3,
        quote: "The Transformer removes recurrence in favour of attention mechanisms.",
      },
    },
    {
      citation_key: "devlin2019bert",
      claim: "BERT was trained exclusively with a next-sentence prediction objective.",
      verdict: "CONTRADICT",
      confidence: 0.89,
      risk_level: "high",
      source_location: {
        page: 3,
        quote: "BERT was trained exclusively with a next-sentence prediction objective.",
        annotation: "Claim contradicts the cited source",
      },
    },
    {
      citation_key: "brown2020language",
      claim: "Larger language models always improve few-shot performance.",
      verdict: "PARTIAL",
      confidence: 0.82,
      risk_level: "medium",
      source_location: {
        page: 3,
        quote: "Larger language models always improve few-shot performance.",
        annotation: "Claim is broader than the evidence",
      },
    },
    {
      citation_key: "lewis2020retrieval",
      claim: "RAG combines parametric and non-parametric memory.",
      verdict: "SUPPORT",
      confidence: 0.91,
      risk_level: "low",
      source_location: {
        page: 4,
        quote: "RAG combines parametric and non-parametric memory.",
      },
    },
    {
      citation_key: "smith2024survey",
      claim: "Citation errors affect a majority of reviewed manuscripts.",
      verdict: "NOT_FOUND",
      confidence: 0.76,
      risk_level: "high",
      source_location: {
        page: 4,
        quote: "Citation errors affect a majority of reviewed manuscripts.",
        annotation: "Source could not be located",
      },
    },
  ],
};
