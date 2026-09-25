"""
Precision AI - Text embeddings.
Default: sentence-transformers all-MiniLM-L6-v2 (local, free, 384-d).
Fallback: a dependency-free hashing embedder (lexical, lower quality) so the system still runs
where torch cannot be installed. Vectors are L2-normalised so inner product == cosine.
"""

import asyncio
import hashlib
import re
from functools import lru_cache
from typing import Protocol

import numpy as np

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class Embedder(Protocol):
    name: str
    dim: int

    def encode(self, texts: list[str]) -> np.ndarray: ...


class SentenceTransformerEmbedder:
    def __init__(self, model_name: str):
        from sentence_transformers import SentenceTransformer  # heavy import, done lazily

        self._model = SentenceTransformer(model_name, device="cpu")
        self.dim = int(self._model.get_embedding_dimension()
                       if hasattr(self._model, "get_embedding_dimension")
                       else self._model.get_sentence_embedding_dimension())
        self.name = f"st:{model_name}"

    def encode(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype="float32")
        vecs = self._model.encode(texts, normalize_embeddings=True, batch_size=32, show_progress_bar=False)
        return np.asarray(vecs, dtype="float32")


class HashingEmbedder:
    """Feature-hashed word unigrams/bigrams + character 4-grams."""

    def __init__(self, dim: int = 768):
        self.dim = dim
        self.name = f"hashing:{dim}"

    def _features(self, text: str) -> list[str]:
        words = re.findall(r"[a-z0-9]+", text.lower())
        feats = [f"w:{w}" for w in words]
        feats += [f"b:{a}_{b}" for a, b in zip(words, words[1:])]
        for w in words:
            padded = f"#{w}#"
            feats += [f"c:{padded[i:i + 4]}" for i in range(max(1, len(padded) - 3))]
        return feats

    def encode(self, texts: list[str]) -> np.ndarray:
        out = np.zeros((len(texts), self.dim), dtype="float32")
        for row, text in enumerate(texts):
            for feat in self._features(text):
                h = int.from_bytes(hashlib.blake2b(feat.encode(), digest_size=8).digest(), "little")
                out[row, h % self.dim] += 1.0 if (h >> 63) & 1 else -1.0
            norm = np.linalg.norm(out[row])
            if norm > 0:
                out[row] /= norm
        return out


@lru_cache()
def get_embedder() -> Embedder:
    settings = get_settings()
    if settings.EMBEDDING_BACKEND == "sentence-transformers":
        try:
            emb = SentenceTransformerEmbedder(settings.EMBEDDING_MODEL)
            logger.info("embedder_loaded", embedder=emb.name, dim=emb.dim)
            return emb
        except Exception as exc:  # missing torch / model download failure
            logger.warning("embedder_fallback_to_hashing", error=str(exc)[:200])
    return HashingEmbedder()


async def embed(texts: list[str]) -> np.ndarray:
    """Encode off the event loop (model inference is CPU-bound)."""
    return await asyncio.to_thread(get_embedder().encode, texts)
