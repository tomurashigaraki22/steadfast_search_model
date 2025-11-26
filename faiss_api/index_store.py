import os
import json
import faiss
import numpy as np
from typing import List, Tuple, Dict
from .config import INDEX_PATH, MAPPING_PATH, DATA_DIR

class FaissIndexStore:
    """
    Manages FAISS index and mapping (faiss_id -> product_id) persistence.
    Vectors are not persisted separately; deletes trigger index rebuild from source rows.
    """

    def __init__(self, dim: int):
        self.dim = dim
        self.index = faiss.IndexFlatIP(dim)
        self.mapping: List[int] = []

    def save(self):
        """
        Persists the FAISS index (.bin) and mapping.json.
        """
        os.makedirs(DATA_DIR, exist_ok=True)
        faiss.write_index(self.index, INDEX_PATH)
        with open(MAPPING_PATH, "w", encoding="utf-8") as f:
            json.dump(self.mapping, f)

    def load_if_exists(self) -> bool:
        """
        Loads persisted index and mapping if both exist and match current dim.
        """
        if not (os.path.exists(INDEX_PATH) and os.path.exists(MAPPING_PATH)):
            return False
        idx = faiss.read_index(INDEX_PATH)
        if idx.d != self.dim:
            return False
        self.index = idx
        with open(MAPPING_PATH, "r", encoding="utf-8") as f:
            self.mapping = json.load(f)
        return True

    def rebuild(self, items: List[Tuple[int, np.ndarray]]):
        """
        Rebuilds the index from (product_id, vector) items.
        """
        self.index = faiss.IndexFlatIP(self.dim)
        self.mapping = []
        if items:
            vecs = np.stack([v for _, v in items], axis=0).astype("float32")
            self.index.add(vecs)
            self.mapping = [pid for pid, _ in items]

    def add(self, product_id: int, vector: np.ndarray):
        """
        Adds a product to the index.
        """
        self.index.add(vector.reshape(1, -1).astype("float32"))
        self.mapping.append(product_id)

    def search(self, vector: np.ndarray, top_k: int) -> List[Tuple[int, float]]:
        """
        Searches the index and returns [(product_id, score), ...].
        """
        if len(self.mapping) == 0:
            return []
        D, I = self.index.search(vector.reshape(1, -1).astype("float32"), top_k)
        results = []
        for score, idx in zip(D[0], I[0]):
            if idx == -1:
                continue
            pid = self.mapping[idx]
            results.append((pid, float(score)))
        return results

