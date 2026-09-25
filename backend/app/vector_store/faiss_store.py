"""
Precision AI - FAISS implementation of the vector store.
IndexIDMap2(IndexFlatIP) over L2-normalised vectors => exact cosine search keyed by DB ids.
Persisted as <dir>/<name>.faiss plus <name>.meta.json (embedder identity + dimension).
"""

import json
from pathlib import Path

import faiss
import numpy as np

from app.vector_store.base import VectorStore


class FaissVectorStore(VectorStore):
    def __init__(self, name: str, dim: int, directory: str, embedder_name: str):
        self.name = name
        self.dim = dim
        self.embedder_name = embedder_name
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.index_path = self.dir / f"{name}.faiss"
        self.meta_path = self.dir / f"{name}.meta.json"
        self.index = self._new_index()

    def _new_index(self):
        return faiss.IndexIDMap2(faiss.IndexFlatIP(self.dim))

    def load(self) -> bool:
        """Load from disk. Returns False if missing or built with a different embedder."""
        if not (self.index_path.exists() and self.meta_path.exists()):
            return False
        try:
            meta = json.loads(self.meta_path.read_text())
            if meta.get("embedder") != self.embedder_name or meta.get("dim") != self.dim:
                return False
            self.index = faiss.read_index(str(self.index_path))
            return True
        except Exception:
            self.index = self._new_index()
            return False

    def upsert(self, ids: list[int], vectors: np.ndarray) -> None:
        if not ids:
            return
        id_arr = np.asarray(ids, dtype="int64")
        self.index.remove_ids(id_arr)  # make re-indexing an id idempotent
        self.index.add_with_ids(np.ascontiguousarray(vectors, dtype="float32"), id_arr)

    def remove(self, ids: list[int]) -> None:
        if ids:
            self.index.remove_ids(np.asarray(ids, dtype="int64"))

    def search(self, vector: np.ndarray, k: int) -> list[tuple[int, float]]:
        if self.index.ntotal == 0 or k <= 0:
            return []
        query = np.ascontiguousarray(vector.reshape(1, -1), dtype="float32")
        scores, ids = self.index.search(query, min(k, self.index.ntotal))
        return [(int(i), float(s)) for i, s in zip(ids[0], scores[0]) if i != -1]

    def ids(self) -> set[int]:
        if self.index.ntotal == 0:
            return set()
        return set(int(i) for i in faiss.vector_to_array(self.index.id_map))

    def reset(self) -> None:
        self.index = self._new_index()

    def persist(self) -> None:
        tmp = self.index_path.with_suffix(".faiss.tmp")
        faiss.write_index(self.index, str(tmp))
        tmp.replace(self.index_path)
        self.meta_path.write_text(json.dumps(
            {"embedder": self.embedder_name, "dim": self.dim, "count": int(self.index.ntotal)}))

    def __len__(self) -> int:
        return int(self.index.ntotal)


def open_store(name: str, dim: int, directory: str, embedder_name: str) -> tuple[FaissVectorStore, bool]:
    store = FaissVectorStore(name, dim, directory, embedder_name)
    loaded = store.load()
    return store, loaded


__all__ = ["FaissVectorStore", "open_store"]
