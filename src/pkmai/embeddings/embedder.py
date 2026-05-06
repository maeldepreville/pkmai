import logging
import os
from collections.abc import Callable

import numpy as np


class LocalEmbedder:
    """
    Wrapper around SentenceTransformers with safer defaults for packaged
    desktop CPU execution.
    """

    def __init__(
        self,
        model_name: str,
        device: str = "cpu",
        max_seq_length: int = 512,
    ):
        os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
        os.environ.setdefault("OMP_NUM_THREADS", "1")
        os.environ.setdefault("MKL_NUM_THREADS", "1")
        os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")

        # Lazy import so env vars are applied before torch/tokenizers load.
        from sentence_transformers import SentenceTransformer

        logging.info("Loading embedding model: %s", model_name)
        self.model = SentenceTransformer(model_name, device=device)

        if hasattr(self.model, "max_seq_length"):
            old_len = self.model.max_seq_length
            self.model.max_seq_length = min(old_len, max_seq_length)
            logging.info(
                "Embedding model max_seq_length set: %s -> %s",
                old_len,
                self.model.max_seq_length,
            )

    def encode_texts(
        self,
        texts: list[str],
        show_progress: bool = False,
        batch_size: int = 4,
        max_chars: int = 8_000,
        status_callback: Callable[[str], None] | None = None,
    ) -> np.ndarray:
        """
        Encode texts in small batches to avoid apparent deadlocks / memory spikes
        in PyInstaller desktop builds.
        """
        if not texts:
            return np.array([], dtype=np.float32)

        safe_texts = [text[:max_chars] for text in texts]

        logging.info(
            "Encoding %d texts with batch_size=%d, max_chars=%d",
            len(safe_texts),
            batch_size,
            max_chars,
        )

        chunks: list[np.ndarray] = []

        for start in range(0, len(safe_texts), batch_size):
            end = min(start + batch_size, len(safe_texts))
            batch = safe_texts[start:end]

            msg = f"Embedding notes {start + 1}-{end}/{len(safe_texts)}"
            logging.info(msg)
            if status_callback is not None:
                status_callback(msg)

            embeddings = self.model.encode(
                batch,
                batch_size=batch_size,
                normalize_embeddings=True,
                convert_to_numpy=True,
                show_progress_bar=show_progress,
            )

            chunks.append(np.asarray(embeddings, dtype=np.float32))

        return np.vstack(chunks)

    @staticmethod
    def cosine_sim_matrix(embeddings: np.ndarray) -> np.ndarray:
        return embeddings @ embeddings.T
