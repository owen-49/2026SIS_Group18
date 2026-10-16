// Abstract excerpts retrieved from the linked ACL publication records.
export const demoSourceProfiles: Record<string, { url: string; doi: string | null; venue: string; totalPages: number; abstract: string; license: string }> = {
  "Peters et al.|2018a": {
    "url": "https://aclanthology.org/N18-1202/",
    "doi": "10.18653/v1/N18-1202",
    "venue": "Proceedings of the 2018 Conference of the North American Chapter of the Association for Computational Linguistics: Human Language Technologies, Volume 1 (Long Papers)",
    "totalPages": 11,
    "abstract": "We introduce a new type of deep contextualized word representation that models both (1) complex characteristics of word use (e.g., syntax and semantics), and (2) how these uses vary across linguistic contexts (i.e., to model polysemy). Our word vectors are learned functions of the internal states of a deep bidirectional language model (biLM), which is pre-trained on a large text corpus. We show that these representations can be easily added to existing models and significantly improve the state of the art across six challenging NLP problems, including question answering, textual entailment and sentiment analysis. We also present an analysis showing that exposing the deep internals of the pre-trained network is crucial, allowing downstream models to mix different types of semi-supervision signals.",
    "license": "CC BY 4.0"
  },
  "Howard and Ruder|2018": {
    "url": "https://aclanthology.org/P18-1031/",
    "doi": "10.18653/v1/P18-1031",
    "venue": "Proceedings of the 56th Annual Meeting of the Association for Computational Linguistics (Volume 1: Long Papers)",
    "totalPages": 12,
    "abstract": "Inductive transfer learning has greatly impacted computer vision, but existing approaches in NLP still require task-specific modifications and training from scratch. We propose Universal Language Model Fine-tuning (ULMFiT), an effective transfer learning method that can be applied to any task in NLP, and introduce techniques that are key for fine-tuning a language model. Our method significantly outperforms the state-of-the-art on six text classification tasks, reducing the error by 18-24% on the majority of datasets. Furthermore, with only 100 labeled examples, it matches the performance of training from scratch on 100 times more data. We open-source our pretrained models and code.",
    "license": "CC BY 4.0"
  },
  "Rajpurkar et al.|2016": {
    "url": "https://aclanthology.org/D16-1264/",
    "doi": "10.18653/v1/D16-1264",
    "venue": "Proceedings of the 2016 Conference on Empirical Methods in Natural Language Processing",
    "totalPages": 10,
    "abstract": "We present the Stanford Question Answering Dataset (SQuAD), a new reading comprehension dataset consisting of 100,000+ questions posed by crowdworkers on a set of Wikipedia articles, where the answer to each question is a segment of text from the corresponding reading passage. We analyze the dataset to understand the types of reasoning required to answer the questions, leaning heavily on dependency and constituency trees. We build a strong logistic regression model, which achieves an F1 score of 51.0%, a signiﬁcant improvement over a simple baseline (20%). However, human performance (86.8%) is much higher, indicating that the dataset presents a good challenge problem for future research. The dataset is freely available at https://stanford-qa.com.",
    "license": "CC BY 4.0"
  },
  "Wang et al.|2018a": {
    "url": "https://aclanthology.org/W18-5446/",
    "doi": "10.18653/v1/W18-5446",
    "venue": "Proceedings of the 2018 EMNLP Workshop BlackboxNLP: Analyzing and Interpreting Neural Networks for NLP",
    "totalPages": 3,
    "abstract": "Human ability to understand language is general, flexible, and robust . In contrast, most NLU models above the word level are designed for a specific task and struggle with out-of-domain data. If we aspire to develop models with understanding beyond the detection of superficial correspondences between inputs and outputs, then it is critical to develop a unified model that can execute a range of linguistic tasks across different domains. To facilitate research in this direction, we present the General Language Understanding Evaluation (GLUE, gluebenchmark.com): a benchmark of nine diverse NLU tasks, an auxiliary dataset for probing models for understanding of specific linguistic phenomena, and an online platform for evaluating and comparing models. For some benchmark tasks, training data is plentiful, but for others it is limited or does not match the genre of the test set. GLUE thus favors models that can represent linguistic knowledge in a way that facilitates sample-efficient learning and effective knowledge-transfer across tasks. While none of the datasets in GLUE were created from scratch for the benchmark, four of them feature privately-held test data, which is used to ensure that the benchmark is used fairly. We evaluate baselines that use ELMo (Peters et al., 2018), a powerful transfer learning technique, as well as state-of-the-art sentence representation models. The best models still achieve fairly low absolute scores. Analysis with our diagnostic dataset yields similarly weak performance over all phenomena tested, with some exceptions.",
    "license": "CC BY 4.0"
  },
  "Pennington et al.|2014": {
    "url": "https://aclanthology.org/D14-1162/",
    "doi": "10.3115/v1/D14-1162",
    "venue": "Proceedings of the 2014 Conference on Empirical Methods in Natural Language Processing (EMNLP)",
    "totalPages": 12,
    "abstract": "Recent methods for learning vector space representations of words have succeeded in capturing ﬁne-grained semantic and syntactic regularities using vector arithmetic, but the origin of these regularities has remained opaque. We analyze and make explicit the model properties needed for such regularities to emerge in word vectors. The result is a new global logbilinear regression model that combines the advantages of the two major model families in the literature: global matrix factorization and local context window methods. Our model efﬁciently leverages statistical information by training only on the nonzero elements in a word-word cooccurrence matrix, rather than on the entire sparse matrix or on individual context windows in a large corpus. The model produces a vector space with meaningful substructure, as evidenced by its performance of 75% on a recent word analogy task. It also outperforms related models on similarity tasks and named entity recognition.",
    "license": "CC BY-NC-SA 3.0"
  }
};
