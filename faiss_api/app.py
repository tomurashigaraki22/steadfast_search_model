import os
import threading
from typing import List, Dict
from flask import Flask, request, jsonify
from flask_cors import CORS
import numpy as np

from .config import DATA_DIR
from .db import fetch_product, fetch_all_products
from .embeddings import get_embedding_for_product, get_embedding_for_query, get_model, get_embedding_dim
from .index_store import FaissIndexStore
from .utils import parse_product_rows_from_sql

app = Flask(__name__)
os.makedirs(DATA_DIR, exist_ok=True)
_allowed_origins = [
    "http://localhost:3000",
    "http://localhost:3001",
    "https://steadfast.ng",
    "https://admin.steadfast.ng",
    "https://padi.steadfast.ng",
]
CORS(app, resources={r"/*": {"origins": _allowed_origins}})

_index: FaissIndexStore = None
_index_ready: bool = False
_index_progress = {"total": 0, "processed": 0}
_index_error: str = ""

def _init_index():
    """
    Initializes FAISS index and loads/creates persistence.
    Builds from MySQL or product_details.sql if no persisted index exists.
    Performs incremental building so API can serve requests early.
    """
    global _index, _index_ready, _index_progress, _index_error
    dim = int(get_embedding_dim())
    store = FaissIndexStore(dim=dim)
    if store.load_if_exists():
        _index = store
        _index_ready = True
        _index_progress = {"total": len(store.mapping), "processed": len(store.mapping)}
        return
    try:
        products: List[Dict]
        try:
            products = fetch_all_products()
        except Exception:
            products = []

        if not products:
            products = parse_product_rows_from_sql()

        _index = store
        _index_progress = {"total": len(products), "processed": 0}

        # Incremental build: add vectors one by one and mark ready after first batch
        batch_threshold = 30
        for row in products:
            try:
                # Skip deleted products
                if str(row.get("is_deleted")) == "1":
                    _index_progress["processed"] += 1
                    continue
                pid = int(row.get("productId") or row.get("id"))
                vec = get_embedding_for_product(row)
                _index.add(pid, vec)
                _index_progress["processed"] += 1
                if not _index_ready and _index_progress["processed"] >= batch_threshold:
                    _index_ready = True
            except Exception:
                _index_progress["processed"] += 1
                continue

        _index_ready = True
        _index.save()
    except Exception as e:
        _index_error = str(e)

def _init_index_background():
    t = threading.Thread(target=_init_index, daemon=True)
    t.start()

@app.route("/add-product/<int:product_id>", methods=["POST"])
def add_product(product_id: int):
    """
    Adds a product to the FAISS index from MySQL by product_id.
    Persists index and mapping.
    """
    global _index
    if not _index_ready:
        return jsonify({"error": "index initializing"}), 503
    row = fetch_product(product_id)
    if not row:
        return jsonify({"error": "product not found"}), 404
    if str(row.get("is_deleted")) == "1":
        return jsonify({"error": "product is deleted"}), 400
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
    if not _index_ready:
        return jsonify({"error": "index initializing"}), 503
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

@app.route("/rebuild", methods=["GET"])
def rebuild_index():
    global _index, _index_ready, _index_progress, _index_error
    def _task():
        global _index, _index_ready, _index_progress, _index_error
        try:
            dim = int(get_embedding_dim())
            store = FaissIndexStore(dim=dim)
            products: List[Dict]
            try:
                products = fetch_all_products()
            except Exception:
                products = []
            if not products:
                products = parse_product_rows_from_sql()
            _index_progress = {"total": len(products), "processed": 0}
            items = []
            for row in products:
                try:
                    pid = int(row.get("productId") or row.get("id"))
                except Exception:
                    _index_progress["processed"] += 1
                    continue
                try:
                    vec = get_embedding_for_product(row)
                except Exception:
                    _index_progress["processed"] += 1
                    continue
                items.append((pid, vec))
                _index_progress["processed"] += 1
            store.rebuild(items)
            store.save()
            _index = store
            _index_ready = True
        except Exception as e:
            _index_error = str(e)
            _index_ready = True
    _index_ready = False
    t = threading.Thread(target=_task, daemon=True)
    t.start()
    return jsonify({"status": "rebuild_started"}), 202

@app.route("/search", methods=["POST"])
def search():
    """
    Searches for similar products.
    Accepts JSON: { "query": "<image URL or text>", "top_k": 5 }
    Returns full product rows with similarity scores.
    """
    global _index
    if not _index_ready:
        return jsonify({"error": "index initializing"}), 503
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

@app.route("/rebuild", methods=["POST"])
def rebuild():
    global _index
    if not _index_ready:
        return jsonify({"error": "index initializing"}), 503
    products: List[Dict]
    try:
        products = fetch_all_products()
    except Exception:
        products = []
    if not products:
        products = parse_product_rows_from_sql()
    items = []
    for p in products:
        try:
            if str(p.get("is_deleted")) == "1":
                continue
            pid = p.get("productId") or p.get("id")
            if pid is None:
                continue
            vec = get_embedding_for_product(p)
            items.append((int(pid), vec))
        except Exception:
            continue
    _index.rebuild(items)
    _index.save()
    return jsonify({"status": "ok", "index_size": len(_index.mapping)})

@app.route("/health", methods=["GET"])
def health():
    size = 0
    if _index and getattr(_index, "mapping", None):
        size = len(_index.mapping)
    return jsonify({
        "status": "ok",
        "index_ready": _index_ready,
        "index_size": size,
        "progress": _index_progress,
        "error": _index_error,
    })

def create_app():
    """
    Returns the Flask app, ensuring index initialization on startup.
    """
    _init_index_background()
    return app

if __name__ == "__main__":
    _init_index_background()
    app.run(host="0.0.0.0", port=9990)
