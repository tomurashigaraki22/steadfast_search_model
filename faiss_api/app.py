import os
from typing import List, Dict
from flask import Flask, request, jsonify
import numpy as np

from .config import DATA_DIR
from .db import fetch_product, fetch_all_products
from .embeddings import get_embedding_for_product, get_embedding_for_query, get_model
from .index_store import FaissIndexStore
from .utils import parse_product_rows_from_sql

app = Flask(__name__)
os.makedirs(DATA_DIR, exist_ok=True)

_index: FaissIndexStore = None

def _init_index():
    """
    Initializes FAISS index and loads/creates persistence.
    Builds from MySQL or product_details.sql if no persisted index exists.
    """
    global _index
    dim = int(get_model().get_sentence_embedding_dimension())
    store = FaissIndexStore(dim=dim)
    if store.load_if_exists():
        _index = store
        return

    products: List[Dict]
    try:
        products = fetch_all_products()
    except Exception:
        products = []

    if not products:
        products = parse_product_rows_from_sql()

    items = []
    for row in products:
        try:
            pid = int(row["id"])
            vec = get_embedding_for_product(row)
            items.append((pid, vec))
        except Exception:
            continue

    store.rebuild(items)
    store.save()
    _index = store

@app.route("/add-product/<int:product_id>", methods=["POST"])
def add_product(product_id: int):
    """
    Adds a product to the FAISS index from MySQL by product_id.
    Persists index and mapping.
    """
    global _index
    if _index is None:
        _init_index()
    row = fetch_product(product_id)
    if not row:
        return jsonify({"error": "product not found"}), 404
    vec = get_embedding_for_product(row)
    _index.add(product_id, vec)
    _index.save()
    return jsonify({"status": "added", "product_id": product_id})

@app.route("/delete-product/<int:product_id>", methods=["POST"])
def delete_product(product_id: int):
    """
    Removes a product from the FAISS index by rebuilding without it.
    Persists index and mapping.
    """
    global _index
    if _index is None:
        _init_index()
    remaining_ids = [pid for pid in _index.mapping if pid != product_id]

    # Try MySQL; fallback to SQL dump for rows
    rows: Dict[int, Dict] = {}
    try:
        for pid in remaining_ids:
            row = fetch_product(pid)
            if row:
                rows[pid] = row
    except Exception:
        pass

    if not rows:
        for row in parse_product_rows_from_sql():
            pid = int(row.get("id"))
            if pid in remaining_ids:
                rows[pid] = row

    items = []
    for pid in remaining_ids:
        row = rows.get(pid)
        if not row:
            continue
        try:
            vec = get_embedding_for_product(row)
            items.append((pid, vec))
        except Exception:
            continue

    _index.rebuild(items)
    _index.save()
    return jsonify({"status": "deleted", "product_id": product_id})

@app.route("/search", methods=["POST"])
def search():
    """
    Searches for similar products.
    Accepts JSON: { "query": "<image URL or text>", "top_k": 5 }
    Returns full product rows with similarity scores.
    """
    global _index
    if _index is None:
        _init_index()
    data = request.get_json(force=True) or {}
    query = str(data.get("query") or "").strip()
    top_k = int(data.get("top_k") or 5)
    if not query:
        return jsonify({"error": "query is required"}), 400
    vec = get_embedding_for_query(query)
    results = _index.search(vec, top_k)
    out = []
    for pid, score in results:
        row = None
        try:
            row = fetch_product(pid)
        except Exception:
            row = None
        if not row:
            for r in parse_product_rows_from_sql():
                if int(r.get("id")) == pid:
                    row = r
                    break
        if row:
            row["_similarity"] = score
            out.append(row)
    return jsonify({"results": out, "count": len(out)})

def create_app():
    """
    Returns the Flask app, ensuring index initialization on startup.
    """
    _init_index()
    return app

if __name__ == "__main__":
    _init_index()
    app.run(host="0.0.0.0", port=8000)

