"""Text embedding with sentence-transformers.

Produces dense vector representations for claims and source passages
to enable semantic (not just keyword) matching.
"""

import numpy as np
from sentence_transformers import SentenceTransformer

# Default model: good balance of speed and semantic quality.
# Alternatives: 'all-mpnet-base-v2' (higher quality, slower)
#               'mixedbread-ai/mxbai-embed-large-v1' (SOTA, needs API key)
DEFAULT_MODEL = "all-MiniLM-L6-v2"

# Dimension of the default model's embeddings
EMBEDDING_DIM = 384


class Embedder:
    """Wraps a sentence-transformers model for ClaimTrace's use case."""

    def __init__(self, model_name: str = DEFAULT_MODEL):
        """Initialize the embedder.

        Args:
            model_name: HuggingFace sentence-transformers model identifier.
        """
        self.model = SentenceTransformer(model_name)
        self.dimension = self.model.get_sentence_embedding_dimension()

    def encode(self, texts: list[str], batch_size: int = 32) -> np.ndarray:
        """Encode a list of texts into embeddings.

        Args:
            texts: List of text strings to embed.
            batch_size: Batch size for encoding.

        Returns:
            NumPy array of shape (len(texts), dimension).
        """
        return self.model.encode(
            texts,
            batch_size=batch_size,
            show_progress_bar=False,
            normalize_embeddings=True,  # L2-normalized for cosine similarity
        )

    def encode_single(self, text: str) -> np.ndarray:
        """Encode a single text string.

        Args:
            text: The text to embed.

        Returns:
            1D NumPy array of shape (dimension,).
        """
        return self.encode([text])[0]
