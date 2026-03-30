import logging
import numpy as np
from sentence_transformers import SentenceTransformer


class LocalEmbedder:
    """
    A wrapper class for SentenceTransformers to handle text embeddings
    and similarity calculations.
    """

    def __init__(self, model_name: str):
        logging.info("Loading embedding model: %s", model_name)
        self.model = SentenceTransformer(model_name)

    def encode_texts(self, texts: list[str], show_progress: bool = True) -> np.ndarray:
        """
        Encodes a list of strings into normalized numpy arrays.
        """
        if not texts:
            return np.array([], dtype=np.float32)

        embeddings = self.model.encode(
            texts,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=show_progress,
        )
        return np.asarray(embeddings, dtype=np.float32)

    @staticmethod
    def cosine_sim_matrix(embeddings: np.ndarray) -> np.ndarray:
        """
        Computes the cosine similarity matrix for a set of normalized embeddings.
        """
        return embeddings @ embeddings.T
