"""
Precision AI - Vector store interface.
A vector store only maps relational row ids -> vectors. It is never the source of truth:
callers always re-fetch the rows from PostgreSQL by id. Swapping FAISS for pgvector means
implementing this interface.
"""

from abc import ABC, abstractmethod

import numpy as np


class VectorStore(ABC):
    name: str
    dim: int

    @abstractmethod
    def upsert(self, ids: list[int], vectors: np.ndarray) -> None: ...

    @abstractmethod
    def remove(self, ids: list[int]) -> None: ...

    @abstractmethod
    def search(self, vector: np.ndarray, k: int) -> list[tuple[int, float]]: ...

    @abstractmethod
    def ids(self) -> set[int]: ...

    @abstractmethod
    def reset(self) -> None: ...

    @abstractmethod
    def persist(self) -> None: ...

    def __len__(self) -> int:
        return len(self.ids())
