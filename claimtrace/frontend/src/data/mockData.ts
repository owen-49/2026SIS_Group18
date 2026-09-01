import type { AuditResponse, LibraryPaper, PaperClaimsResponse, PaperRecord, SourceDocument, VerifyResponse } from "../types/api";

export const demoManuscript: PaperRecord = {
  paper_id: "paper-manuscript",
  original_filename: "transformer-literature-review.pdf",
  file_type: "pdf",
  file_size: 1_640_000,
  status: "completed",
  pages: 12,
  paragraph_count: 146,
  entry_count: 0,
  title: "Transformer Literature Review",
  error_message: null,
  created_at: "2026-08-16T04:30:00.000Z",
  updated_at: "2026-08-16T04:30:00.000Z",
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
  manuscript_id: demoManuscript.paper_id,
  status: "completed",
  error_message: null,
  claims: [
    {
      claim_id: "claim-attention",
      text: "Self-attention enables the model to relate information from different positions in a sequence without recurrence.",
      page: 3,
      citation_marker: "[1]",
      resolution_status: "identified",
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
    },
    {
      claim_id: "claim-bert",
      text: "Bidirectional pre-training allows language models to use both left and right context when representing each token.",
      page: 5,
      citation_marker: "[2]",
      resolution_status: "identified",
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
    },
    {
      claim_id: "claim-missing",
      text: "Citation-aware review eliminates most referencing errors before peer review.",
      page: 9,
      citation_marker: "[8]",
      resolution_status: "not_found",
      cited_source: null,
      similar_sources: [
        {
          source_paper_id: "candidate-citation-checking",
          citation_key: "wright2024citation",
          title: "Automatic Citation Checking in Scientific Documents",
          authors: ["Daniel Wright", "Mina Chen"],
          venue: "Information Processing & Management",
          year: 2024,
          doi: "10.1016/j.ipm.2024.103765",
          url: "https://doi.org/10.1016/j.ipm.2024.103765",
          database: "Crossref",
          similarity: 0.88,
        },
        {
          source_paper_id: "candidate-reference-quality",
          citation_key: "lee2023reference",
          title: "Reference Quality Assessment for Scholarly Writing",
          authors: ["Sora Lee", "Nikhil Rao", "Emma Davis"],
          venue: "Scientometrics",
          year: 2023,
          doi: null,
          url: null,
          database: "Semantic Scholar",
          similarity: 0.79,
        },
      ],
    },
  ],
};

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

const demoSourceDocuments: Record<string, SourceDocument> = {
  attention: {
    total_pages: 3,
    matched_location: { page: 3, paragraph_index: 1 },
    pages: [
      { page: 1, heading: "Abstract", paragraphs: ["A sequence transduction architecture is introduced that replaces recurrence with attention, allowing training to be parallelised across token positions.", "The approach is evaluated on translation tasks and provides a simpler path for modelling long-range dependencies."] },
      { page: 2, heading: "1. Introduction", paragraphs: ["Recurrent models process tokens in order, which limits parallel computation within a sequence.", "Attention mechanisms provide a way to connect positions directly and reduce the path length between related tokens."] },
      { page: 3, heading: "2. Model Architecture", paragraphs: ["The encoder and decoder are composed from stacked attention and feed-forward layers.", "We propose a new simple network architecture, the Transformer, based solely on attention mechanisms, dispensing with recurrence and convolutions entirely.", "Residual connections and normalisation are applied around each sub-layer."] },
    ],
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

const demoReviewManuscriptDocument: SourceDocument = {
  total_pages: 12,
  matched_location: null,
  pages: [
    { page: 1, heading: "AI in Scientific Discovery", paragraphs: ["A citation-aware review of language models, retrieval systems, and evidence validation.", "Abstract — Artificial intelligence increasingly supports literature discovery, hypothesis generation, and scientific writing. This paper reviews recent systems and examines how accurately their claims remain connected to published evidence.", "Keywords: scientific discovery, language models, citation verification, retrieval-augmented generation."] },
    { page: 2, heading: "1. Introduction", paragraphs: ["Scientific knowledge is growing faster than any individual researcher can read. Machine-assisted discovery tools help organise this literature and surface connections between distant fields.", "Reliable citation practice remains essential. A fluent sentence may overstate, misread, or cite a source that does not contain the claimed evidence.", "We study a workflow that connects every cited claim to its source passage and presents questionable citations for human review."] },
    { page: 3, heading: "2. Attention-based Models", paragraphs: ["Sequence modelling has traditionally relied on recurrent or convolutional architectures to represent dependencies between tokens.", "Self-attention enables the model to relate information from different positions in a sequence without recurrence.", "This architecture makes it possible to model long-range relationships while allowing substantially more parallel computation."] },
    { page: 4, heading: "3. Retrieval-Augmented Models", paragraphs: ["Retrieval-augmented generation combines parametric and non-parametric memory and allows a model to consult external documents during generation.", "Retrieved passages are combined with the model state before each response, allowing external evidence to contribute facts without permanently changing model parameters.", "Evidence provenance remains necessary because retrieval alone does not guarantee that a generated statement accurately reflects its source."] },
    { page: 5, heading: "4. Contextual Representation", paragraphs: ["Pre-trained language models differ in how much surrounding context is available when a token representation is constructed.", "Bidirectional pre-training allows language models to use both left and right context when representing each token.", "The resulting representations can then be fine-tuned for a wide range of downstream language understanding tasks."] },
    { page: 6, heading: "5. Methodology", paragraphs: ["The review pipeline separates manuscript parsing, citation extraction, source retrieval, and evidence comparison into independent stages.", "Each manuscript sentence is associated with its citation marker and page location. Candidate evidence passages are retrieved from the identified source document.", "The final interface preserves manuscript context so researchers can inspect a result without losing their place in the paper."] },
    { page: 7, heading: "6. Experimental Setup", paragraphs: ["We evaluate the workflow on a small collection of academic manuscripts containing supported, partially supported, contradictory, and missing-source examples.", "Reviewers label each claim using the cited paper and record whether the system identifies the correct manuscript location.", "Interface measurements include time to locate a citation, correction accuracy, and agreement between reviewers."] },
    { page: 8, heading: "7. Results", paragraphs: ["Context-preserving review reduced the time required to locate flagged claims. Reviewers moved directly from a finding to the corresponding sentence.", "Supported claims were typically resolved quickly, while partially supported claims required closer inspection of scope and qualifications.", "Missing documents remained the most common reason that a citation could not be fully assessed."] },
    { page: 9, heading: "8. Limitations", paragraphs: ["Automated checking may help authors discover mismatched references before a manuscript is submitted.", "Citation-aware review eliminates most referencing errors before peer review.", "However, the cited record must first be confirmed before this statement can be treated as evidence-backed."] },
    { page: 10, heading: "9. Discussion", paragraphs: ["Citation verification should support scholarly judgement rather than replace it. Automated signals are most useful when they reveal evidence and preserve uncertainty.", "Showing the original manuscript is essential because a claim can only be interpreted correctly within its surrounding argument.", "A practical system should distinguish model-generated signals from verified bibliographic facts."] },
    { page: 11, heading: "10. Conclusion", paragraphs: ["Evidence-aware citation review can make scholarly writing more transparent and easier to audit.", "The most useful interface links each finding to the exact sentence, citation marker, source document, and supporting passage.", "Future work will evaluate the complete pipeline on larger, expert-reviewed datasets."] },
    { page: 12, heading: "References", paragraphs: ["[1] Vaswani, A. et al. Attention Is All You Need. NeurIPS, 2017.", "[2] Devlin, J. et al. BERT: Pre-training of Deep Bidirectional Transformers. NAACL, 2019.", "[3] Lewis, P. et al. Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks. NeurIPS, 2020."] },
  ],
};

demoPaperClaims.manuscript_document = demoReviewManuscriptDocument;
demoPaperClaims.claims[0].source_document = demoSourceDocuments.attention;
demoPaperClaims.claims[0].manuscript_location = { page: 3, paragraph_index: 1 };
demoPaperClaims.claims[1].source_document = demoSourceDocuments.bert;
demoPaperClaims.claims[1].manuscript_location = { page: 5, paragraph_index: 1 };
demoPaperClaims.claims[2].source_document = null;
demoPaperClaims.claims[2].manuscript_location = { page: 9, paragraph_index: 1 };

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
