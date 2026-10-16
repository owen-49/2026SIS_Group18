import { createDemoCitations, createDemoAudit } from "./demoCitations";
import bertFullMarkdown from "../assets/demo/bert-full.md?raw";
import bertOriginalPdf from "../assets/demo/bert-naacl2019.pdf";
import { fullBertDocument, fullBertClaimLocation } from "../assets/demo/bert-document";
import type { AuditResponse, LibraryPaper, PaperClaimsResponse, PaperRecord, SourceDocument, VerifyResponse } from "../types/api";

export const demoManuscript: PaperRecord = {
  "paper_id": "paper-manuscript",
  "original_filename": "BERT-Devlin-et-al-NAACL-2019.pdf",
  "file_type": "pdf",
  "scope": "library",
  "file_size": 786279,
  "status": "completed",
  "pages": 16,
  "paragraph_count": 9,
  "entry_count": 0,
  "title": "BERT: Pre-training of Deep Bidirectional Transformers for Language Understanding",
  "error_message": null,
  "created_at": "2026-10-16T01:00:00.000Z",
  "updated_at": "2026-10-16T01:00:00.000Z"
};

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

export const demoPaperClaims: PaperClaimsResponse = {
  "manuscript_id": "paper-manuscript",
  "status": "completed",
  "error_message": null,
  "claims": [
    {
      "claim_id": "claim-attention",
      "text": "BERT’s model architecture is a multi-layer bidirectional Transformer encoder based on the original implementation described in Vaswani et al. (2017) and released in the tensor2tensor library.",
      "page": 3,
      "citation_marker": "Vaswani et al. (2017)",
      "resolution_status": "identified",
      "cited_source": {
        "source_paper_id": "paper-attention",
        "citation_key": "vaswani2017attention",
        "title": "Attention Is All You Need",
        "authors": [
          "Ashish Vaswani",
          "Noam Shazeer",
          "Niki Parmar",
          "Jakob Uszkoreit",
          "Llion Jones",
          "Aidan N. Gomez",
          "Łukasz Kaiser",
          "Illia Polosukhin"
        ],
        "venue": "NeurIPS",
        "year": 2017,
        "doi": null,
        "url": "https://papers.nips.cc/paper_files/paper/2017/hash/3f5ee243547dee91fbd053c1c4a845aa-Abstract.html",
        "database": "NeurIPS proceedings"
      },
      "source_document": {
        "total_pages": 11,
        "matched_location": {
          "page": 2,
          "paragraph_index": 0
        },
        "pages": [
          {
            "page": 2,
            "heading": "3.1 Encoder and Decoder Stacks · selected excerpt",
            "paragraphs": [
              "The encoder is composed of a stack of N = 6 identical layers."
            ]
          }
        ]
      },
      "manuscript_location": {
        "page": 3,
        "paragraph_index": 1
      }
    }
  ]
};

export const demoVerification: VerifyResponse = {
  "claim": "BERT’s model architecture is a multi-layer bidirectional Transformer encoder based on the original implementation described in Vaswani et al. (2017) and released in the tensor2tensor library.",
  "verdict": "PARTIAL",
  "confidence": 0.86,
  "rationale": "The source supports a stacked encoder architecture. This short excerpt does not establish every detail of BERT’s bidirectional implementation or its use of tensor2tensor; those details need further review.",
  "matches": [
    {
      "passage_text": "The encoder is composed of a stack of N = 6 identical layers.",
      "similarity": 0.91,
      "entailment_label": "PARTIAL",
      "confidence": 0.86
    }
  ]
};

const demoSourceDocuments: Record<string, SourceDocument> = {
  attention: {
  "total_pages": 11,
  "matched_location": {
    "page": 2,
    "paragraph_index": 0
  },
  "pages": [
    {
      "page": 2,
      "heading": "3.1 Encoder and Decoder Stacks · selected excerpt",
      "paragraphs": [
        "The encoder is composed of a stack of N = 6 identical layers."
      ]
    }
  ]
},
  bert: {
    total_pages: 3,
    matched_location: { page: 3, paragraph_index: 1 },
    pages: [
      { page: 1, heading: "Abstract", paragraphs: ["A bidirectional representation model is pre-trained from unlabelled text and adapted to downstream language understanding tasks.", "The representation conditions on context from both directions rather than using only left-to-right context."] },
      { page: 2, heading: "1. Introduction", paragraphs: ["Pre-trained representations can be used as features or fine-tuned together with a task-specific output layer.", "The model design makes a minimal number of task-specific changes during fine-tuning."] },
      { page: 3, heading: "3. Pre-training BERT", paragraphs: ["Training examples are constructed from BooksCorpus and English Wikipedia.", "BERT is pre-trained using two unsupervised tasks: masked language modelling and next sentence prediction.", "Masked tokens are predicted from their bidirectional context while the sentence-level task models relationships between segments."] },
    ],
  },
  gpt3: {
    total_pages: 3,
    matched_location: { page: 2, paragraph_index: 1 },
    pages: [
      { page: 1, heading: "Abstract", paragraphs: ["Scaling an autoregressive language model is studied as an alternative to task-specific fine-tuning.", "Performance is measured in zero-shot, one-shot, and few-shot settings across multiple tasks."] },
      { page: 2, heading: "1. Introduction", paragraphs: ["Larger models often make more effective use of examples supplied in natural-language context.", "Increasing model capacity improves task-agnostic, few-shot performance, sometimes even reaching competitiveness with prior state-of-the-art fine-tuning approaches.", "The reported gains vary by task and do not establish a universal guarantee for every model or dataset."] },
      { page: 3, heading: "2. Approach", paragraphs: ["The evaluation uses the model without gradient updates or task-specific fine-tuning.", "Examples and instructions are represented directly in the text context used for prediction."] },
    ],
  },
  rag: {
    total_pages: 3,
    matched_location: { page: 2, paragraph_index: 1 },
    pages: [
      { page: 1, heading: "Abstract", paragraphs: ["A generation model is augmented with an external dense vector index of retrieved passages.", "The combined model is evaluated on knowledge-intensive language tasks."] },
      { page: 2, heading: "1. Introduction", paragraphs: ["Parametric models store knowledge in their weights but do not provide direct provenance for individual predictions.", "We combine pre-trained parametric and non-parametric memory for language generation.", "Retrieved documents can be inspected and updated separately from the generator parameters."] },
      { page: 3, heading: "2. Methods", paragraphs: ["A retriever supplies candidate passages and a sequence-to-sequence model conditions generation on those passages.", "The latent document can remain fixed for a sequence or vary between generated tokens."] },
    ],
  },
};

export const demoReviewManuscriptDocument: SourceDocument = fullBertDocument;

demoPaperClaims.manuscript_document = demoReviewManuscriptDocument;
demoPaperClaims.claims[0].manuscript_location = fullBertClaimLocation;
demoManuscript.paragraph_count = fullBertDocument.pages.reduce((count, page) => count + page.paragraphs.length, 0);
const citationDemo = createDemoCitations(demoPaperClaims.claims[0]);
demoPaperClaims.claims = citationDemo.claims;
export const demoCitationGroups = citationDemo.groups;

export const demoClaimAudit = {
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
      cited_source: {
        source_paper_id: "paper-attention",
        citation_key: "vaswani2017attention",
        title: "Attention Is All You Need",
        authors: ["Ashish Vaswani", "Noam Shazeer", "Niki Parmar", "et al."],
        venue: "NeurIPS",
        year: 2017,
        doi: null,
        url: "https://arxiv.org/abs/1706.03762",
        database: "Semantic Scholar",
      },
      source_passage: "We propose a new simple network architecture, the Transformer, based solely on attention mechanisms, dispensing with recurrence and convolutions entirely.",
      source_document: demoSourceDocuments.attention,
      comparison_rationale: "The cited passage directly supports the manuscript statement that the architecture removes recurrence in favour of attention.",
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
      cited_source: {
        source_paper_id: "paper-bert",
        citation_key: "devlin2019bert",
        title: "BERT: Pre-training of Deep Bidirectional Transformers",
        authors: ["Jacob Devlin", "Ming-Wei Chang", "Kenton Lee", "Kristina Toutanova"],
        venue: "NAACL",
        year: 2019,
        doi: "10.18653/v1/N19-1423",
        url: "https://aclanthology.org/N19-1423",
        database: "Semantic Scholar",
      },
      source_passage: "BERT is pre-trained using two unsupervised tasks: masked language modelling and next sentence prediction.",
      source_document: demoSourceDocuments.bert,
      comparison_rationale: "The cited article describes two pre-training objectives, so the word exclusively in the manuscript is contradicted.",
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
      cited_source: {
        source_paper_id: "paper-gpt3",
        citation_key: "brown2020language",
        title: "Language Models are Few-Shot Learners",
        authors: ["Tom Brown", "Benjamin Mann", "Nick Ryder", "et al."],
        venue: "NeurIPS",
        year: 2020,
        doi: null,
        url: "https://arxiv.org/abs/2005.14165",
        database: "Semantic Scholar",
      },
      source_passage: "Increasing model capacity improves task-agnostic, few-shot performance, sometimes even reaching competitiveness with prior state-of-the-art fine-tuning approaches.",
      source_document: demoSourceDocuments.gpt3,
      comparison_rationale: "The source reports improvement in evaluated settings but does not establish that larger models always improve performance.",
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
      cited_source: {
        source_paper_id: "paper-rag",
        citation_key: "lewis2020retrieval",
        title: "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks",
        authors: ["Patrick Lewis", "Ethan Perez", "Aleksandra Piktus", "et al."],
        venue: "NeurIPS",
        year: 2020,
        doi: null,
        url: "https://arxiv.org/abs/2005.11401",
        database: "Semantic Scholar",
      },
      source_passage: "We combine pre-trained parametric and non-parametric memory for language generation.",
      source_document: demoSourceDocuments.rag,
      comparison_rationale: "The source uses the same distinction between parametric and non-parametric memory and directly supports the claim.",
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
      cited_source: null,
      source_passage: null,
      source_document: null,
      comparison_rationale: "The cited record could not be confirmed in the connected academic databases, so the claim cannot be compared with an original source.",
      similar_sources: [
        {
          source_paper_id: "candidate-citation-errors",
          citation_key: "liu2023citationerrors",
          title: "Citation Errors in Scientific Manuscripts: A Systematic Review",
          authors: ["Mei Liu", "Robert Evans"],
          venue: "Research Integrity and Peer Review",
          year: 2023,
          doi: null,
          url: null,
          database: "Semantic Scholar",
          similarity: 0.86,
        },
      ],
    },
  ],
};

export const demoAudit: AuditResponse = createDemoAudit();

export function demoSelectionVerification(claimId: string, selectedText: string): VerifyResponse {
  if (claimId === "claim-attention") return { ...demoVerification, claim: selectedText };
  const claim = demoPaperClaims.claims.find(item => item.claim_id === claimId);
  const passage = claim?.source_document?.pages[0]?.paragraphs[0];
  if (passage) {
    // These cases are tied to the published sentences and source excerpts.
    // A source abstract cannot establish BERT's comparative results or training details.
    const title = claim.cited_source!.title.toLowerCase();
    const text = claim.text;
    const sentences = passage.split(/(?<=[.!?])\s+(?=[A-Z])/);
    let verdict: "SUPPORT" | "PARTIAL" = "PARTIAL";
    let confidence = .82;
    let rationale = "The passage describes the cited work, but does not establish every comparison or implementation detail in this sentence.";
    let evidence = sentences.slice(0, 2).join(" ");
    if (title.includes("contextualized word")) {
      evidence = sentences.slice(1, 3).join(" ");
      if (/^Language model pre-training|^The feature-based approach|^When integrating contextual/.test(text)) {
        verdict = "SUPPORT"; confidence = .94;
        rationale = "The source explains that pre-trained contextual representations can be added to existing models and improve six NLP tasks, supporting the claim about ELMo.";
      } else {
        rationale = "The source describes a pre-trained bidirectional language model. This abstract does not establish the stated architectural comparison with BERT or the exact concatenation procedure.";
      }
    } else if (title.includes("universal language")) {
      evidence = sentences.slice(1, 3).join(" ");
      if (/^Language model pre-training|^More recently/.test(text)) {
        verdict = "SUPPORT"; confidence = .92;
        rationale = "ULMFiT is presented as language-model fine-tuning for downstream tasks, with improvements across six text-classification datasets.";
      } else {
        rationale = "The source supports language-model fine-tuning, but the quoted abstract does not describe the auto-encoder objectives mentioned in this sentence.";
      }
    } else if (title.includes("squad:")) {
      evidence = sentences[0];
      if (/^The Stanford Question Answering Dataset/.test(text)) {
        verdict = "SUPPORT"; confidence = .96;
        rationale = "The source explicitly describes more than 100,000 crowdworker questions on Wikipedia, with answers taken as text spans from the passage.";
      } else {
        confidence = .87;
        rationale = "The source confirms the SQuAD reading-comprehension dataset and answer-span format. It does not establish the other datasets, model scores or QNLI conversion mentioned here.";
      }
    } else if (title.includes("glue:")) {
      evidence = sentences.find(sentence => sentence.startsWith("To facilitate research")) || sentences[0];
      if (/^The General Language Understanding Evaluation/.test(text)) {
        verdict = "SUPPORT"; confidence = .95;
        rationale = "The source explicitly defines GLUE as a benchmark of nine diverse natural language understanding tasks.";
      } else {
        confidence = .85;
        rationale = "The passage confirms GLUE's benchmark and task coverage. Exact GPT rankings and individual dataset conversions need the corresponding results or task descriptions.";
      }
    } else if (title.includes("glove:")) {
      evidence = sentences.slice(0, 3).join(" ");
      confidence = .89;
      rationale = "GloVe is described as a word-representation model. The wider historical claim also cites several other methods, which require their own source checks.";
    }
    return { claim: selectedText, verdict, confidence, rationale,
      matches: [{ passage_text: evidence, similarity: verdict === "SUPPORT" ? .94 : .88, entailment_label: verdict, confidence }],
    };
  }
  return { claim: selectedText, verdict: "NOT_FOUND", confidence: 0, rationale: "The source text is unavailable for comparison.", matches: [] };
}

export function demoCitationComparison(request: import("../types/api").CitationComparisonRequest): import("../types/api").CitationComparisonResponse {
  const claim = demoPaperClaims.claims.find((entry) => entry.claim_id === request.claim_id);
  const judged = Boolean(claim?.source_document?.pages.length);
  const sample = demoSelectionVerification(request.claim_id, request.claim);
  return {
    claim: request.claim, claim_id: request.claim_id, citation_marker: request.citation_marker,
    citation_key: claim?.cited_source?.citation_key || null,
    status: judged ? "COMPARED" : claim?.cited_source ? "SOURCE_NOT_AVAILABLE" : "REFERENCE_NOT_FOUND",
    message: judged ? "The selected claim has been compared with the cited source passage." : claim?.cited_source ? "Reference identified. Add the source PDF to compare this claim against its text." : "This citation could not be linked to an entry in the extracted bibliography. Review the reference details.",
    cited_source: claim?.cited_source || null, source_paper_id: claim?.cited_source?.source_paper_id || null,
    source_document: claim?.source_document || null,
    judgement: judged ? { verdict: sample.verdict, confidence: sample.confidence, rationale: sample.rationale } : null,
    evidence: judged ? sample.matches.map((match, rank) => ({ passage_text: match.passage_text, similarity: match.similarity, rank, page: claim?.source_document?.matched_location?.page || 1 })) : [],
  };
}


const fullBertImages = import.meta.glob<string>("../assets/demo/*.png", { eager: true, query: "?url", import: "default" });
export const demoManuscriptImages: Record<string, string> = Object.fromEntries(
  Object.entries(fullBertImages).map(([path, url]) => [path.split("/").pop()!, url]),
);
export const demoOriginalPdfUrl = bertOriginalPdf;
export const demoRichParagraphLocations = citationDemo.locations;

export const demoManuscriptMarkdown = [
  `# ${demoManuscript.title}`,
  `[Open original PDF](${bertOriginalPdf}) · [Publication record](https://aclanthology.org/N19-1423/)`,
  citationDemo.decorate(bertFullMarkdown),
  "Text and figures: Devlin et al., 2019 / Association for Computational Linguistics. [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Full text converted locally; figure and table regions cropped from the original PDF. Consult the original PDF for exact typography.",
].join("\n\n");
