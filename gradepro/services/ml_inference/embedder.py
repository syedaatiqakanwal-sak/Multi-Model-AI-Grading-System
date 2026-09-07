import os
import numpy as np
import torch
from sentence_transformers import SentenceTransformer


class SlidingWindowEmbedder:
    """
    Produces a single 384-dim embedding for any-length text using a sliding window.

    Why:
      bge-small-en-v1.5 has a 512-token limit. A student's Task 1 answer at 700 words
      is ~950 tokens — the naive approach reads only the first half.

    How:
      1. Tokenise the full text.
      2. Slice into 400-token chunks with 64-token overlap.
      3. Embed each chunk independently (batched for speed).
      4. Mean-pool chunk embeddings → one 384-dim vector.

    Result: The model reads the entire submission, not just the opening paragraph.
    """

    CHUNK_TOKENS = 400
    OVERLAP_TOKENS = 64
    BATCH_SIZE = 32

    def __init__(self, model_name: str = "BAAI/bge-small-en-v1.5"):
        torch.set_num_threads(max(os.cpu_count() or 4, 4))
        self.model = SentenceTransformer(model_name, device="cpu")
        self.tokenizer = self.model.tokenizer

    def encode(self, text: str) -> np.ndarray:
        if not text or not str(text).strip():
            return np.zeros(384, dtype=np.float32)

        text = str(text).strip()

        # Tokenise without special tokens so we can slice cleanly
        tokens = self.tokenizer.encode(text, add_special_tokens=False)

        # If it fits in one chunk, encode directly — faster path
        if len(tokens) <= self.CHUNK_TOKENS:
            with torch.no_grad():
                emb = self.model.encode(
                    text,
                    normalize_embeddings=True,
                    show_progress_bar=False,
                    convert_to_numpy=True,
                )
            return emb.astype(np.float32)

        # Build overlapping chunks
        step = self.CHUNK_TOKENS - self.OVERLAP_TOKENS
        chunks = []
        for start in range(0, len(tokens), step):
            chunk_tokens = tokens[start: start + self.CHUNK_TOKENS]
            if not chunk_tokens:
                break
            chunk_text = self.tokenizer.decode(chunk_tokens, skip_special_tokens=True)
            if chunk_text.strip():
                chunks.append(chunk_text)

        if not chunks:
            return np.zeros(384, dtype=np.float32)

        # Batch-embed all chunks, then mean-pool
        with torch.no_grad():
            embeddings = self.model.encode(
                chunks,
                batch_size=self.BATCH_SIZE,
                normalize_embeddings=True,
                show_progress_bar=False,
                convert_to_numpy=True,
            )

        pooled = np.mean(embeddings, axis=0).astype(np.float32)
        # Re-normalise after mean-pooling
        norm = np.linalg.norm(pooled)
        if norm > 0:
            pooled = pooled / norm
        return pooled

    def encode_dataset_tasks(self, texts: list, batch_size: int = 128) -> np.ndarray:
        """
        Ultra-fast batch encoder for training pipeline.
        Each text goes through the full sliding-window path.
        """
        results = []
        # Batch the individual encode calls
        for i in range(0, len(texts), batch_size):
            batch = texts[i: i + batch_size]
            batch_embs = np.stack([
                self.encode(str(t) if (t is not None and str(t).strip()) else "No response provided.")
                for t in batch
            ])
            results.append(batch_embs)
        return np.vstack(results).astype(np.float32)


_embedder = None


def get_embedder() -> SlidingWindowEmbedder:
    global _embedder
    if _embedder is None:
        _embedder = SlidingWindowEmbedder()
    return _embedder
