"""Semantic retrieval over source paper passages.

Given a claim and a pre-built FAISS index of source paper passages,
returns the most semantically similar passages — even when the
wording is completely different from the claim.
"""

import re
from dataclasses import dataclass

import faiss
import numpy as np

from .embedder import Embedder

# A passage needs at least this many words of three or more letters to be
# indexed. PDF text extraction splits display formulas, axis labels and table
# headers into their own "paragraphs" ("sign(∇xJ(θ,x,y))", "MI-FGSM"); they
# carry no claim the model could judge, yet a short query embeds close to them
# and they crowd real prose out of the top-k evidence.
MIN_PROSE_WORDS = 4
_WORD_RE = re.compile(r"[^\W\d_]{3,}")


def is_prose(passage: str) -> bool:
    """Whether a passage has enough running text to serve as evidence."""
    return len(_WORD_RE.findall(passage)) >= MIN_PROSE_WORDS


@dataclass
class RetrievalResult:
    """A single retrieval result."""

    passage: str
    score: float  # cosine similarity (0-1)
    rank: int
    passage_index: int  # original index in the source passages list


class Retriever:
    """Semantic search over a source paper's passages."""

    def __init__(self, embedder: Embedder | None = None):
        """Initialize the retriever.

        Args:
            embedder: Embedder instance. Creates default if not provided.
        """
        self.embedder = embedder or Embedder()
        self.index: faiss.IndexFlatIP | None = None
        self.passages: list[str] = []
        # Positions in ``passages`` that are in the index, in index order.
        self._indexed: list[int] = []

    def build_index(self, passages: list[str]) -> None:
        """Build a FAISS index from source paper passages.

        Uses inner product (equivalent to cosine similarity with
        L2-normalized embeddings).

        Args:
            passages: List of passage strings from the source paper.
        """
        self.passages = passages
        if not passages:
            self.index = None
            self._indexed = []
            return

        # Fragments are left out of the index, never out of ``passages``:
        # ``passage_index`` must keep pointing into the caller's list, because
        # that position is what maps evidence back to a page. If nothing reads
        # as prose, index everything rather than return no evidence at all.
        self._indexed = [i for i, p in enumerate(passages) if is_prose(p)] or list(
            range(len(passages))
        )
        embeddings = self.embedder.encode([passages[i] for i in self._indexed])
        self.index = faiss.IndexFlatIP(embeddings.shape[1])
        self.index.add(embeddings.astype(np.float32))

    def retrieve(self, claim: str, k: int = 5) -> list[RetrievalResult]:
        """Retrieve the top-k most semantically similar passages.

        Args:
            claim: The claim text from the paper being audited.
            k: Number of passages to retrieve.

        Returns:
            List of RetrievalResult sorted by descending similarity.
        """
        if self.index is None or not self.passages:
            return []

        query_emb = self.embedder.encode([claim]).astype(np.float32)
        scores, indices = self.index.search(query_emb, min(k, len(self._indexed)))

        results: list[RetrievalResult] = []
        for rank, (score, idx) in enumerate(zip(scores[0], indices[0])):
            if idx < 0 or idx >= len(self._indexed):
                continue
            position = self._indexed[idx]
            results.append(
                RetrievalResult(
                    passage=self.passages[position],
                    score=float(score),
                    rank=rank + 1,
                    passage_index=position,
                )
            )

        return results

    def retrieve_with_sentences(
        self, claim: str, k_paragraphs: int = 3, k_sentences: int = 5
    ) -> list[RetrievalResult]:
        """Two-stage retrieval: paragraphs → then best sentences within them.

        Stage 1: Retrieve top-k_paragraphs at paragraph level.
        Stage 2: Split each paragraph into sentences, re-rank against claim.

        Args:
            claim: The claim text.
            k_paragraphs: Number of paragraphs to retrieve in stage 1.
            k_sentences: Total number of sentences to return in stage 2.

        Returns:
            Top-k_sentences ordered by similarity to the claim.
        """
        if self.index is None or not self.passages:
            return []

        # Stage 1: paragraph-level retrieval
        para_results = self.retrieve(claim, k=k_paragraphs)

        # Stage 2: split into sentences, build mini-index, re-rank
        all_sentences: list[tuple[str, int]] = []  # (sentence, para_index)
        for r in para_results:
            # Simple sentence splitting on period
            sents = [s.strip() for s in r.passage.replace("\n", " ").split(". ") if s.strip()]
            for sent in sents:
                if len(sent.split()) > 3:  # skip fragments
                    all_sentences.append((sent, r.passage_index))

        if not all_sentences:
            return para_results

        sent_texts = [s[0] for s in all_sentences]
        sent_embs = self.embedder.encode(sent_texts).astype(np.float32)

        mini_index = faiss.IndexFlatIP(sent_embs.shape[1])
        mini_index.add(sent_embs)

        query_emb = self.embedder.encode([claim]).astype(np.float32)
        scores, indices = mini_index.search(query_emb, min(k_sentences, len(sent_texts)))

        results: list[RetrievalResult] = []
        for rank, (score, idx) in enumerate(zip(scores[0], indices[0])):
            if idx < 0 or idx >= len(sent_texts):
                continue
            text, para_idx = all_sentences[idx]
            results.append(
                RetrievalResult(
                    passage=text,
                    score=float(score),
                    rank=rank + 1,
                    passage_index=para_idx,
                )
            )

        return results
